"""
Construção do pipeline GStreamer (NVENC do Jetson) e gestão dos processos de streaming.

Em vez de bindings PyGObject, fazemos shell-out ao `gst-launch-1.0` com uma lista
de argumentos (sem shell), o que reproduz exactamente os pipelines validados à mão
e evita problemas de quoting.

Pipeline base (validado no Jetson Orin NX):
    rtspsrc -> rtph264depay -> h264parse -> nvv4l2decoder ->
    [overlay opcional em sysmem] -> nvvidconv (NVMM, scale) ->
    nvv4l2h264enc (NVENC) -> h264parse -> flvmux -> rtmpsink
    (+ audiotestsrc silêncio -> aac -> mux)
"""
from __future__ import annotations

import glob
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from .config import settings
from .models import Court

_RESOLUTIONS = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
}

# Posições Pango (gravity) para clockoverlay/textoverlay
_H_ALIGN = {"Left": "left", "Center": "center", "Right": "right"}
_V_ALIGN = {"Top": "top", "Bottom": "bottom"}


def build_rtsp_url(court: Court) -> str:
    """rtsp://user:pass@ip<path> — password URL-encoded (pode ter @, #, etc.)."""
    path = court.rtsp_path or settings.default_rtsp_path
    if not path.startswith("/"):
        path = "/" + path
    user = quote(court.nvr_user or "", safe="")
    pwd = quote(court.nvr_password or "", safe="")
    return f"rtsp://{user}:{pwd}@{court.camera_ip}{path}"


def _split_position(pos: str) -> tuple[str, str]:
    """'BottomLeft' -> ('bottom','left'). Default bottom/left."""
    v = "bottom"
    h = "left"
    for key, val in _V_ALIGN.items():
        if pos.startswith(key):
            v = val
            rest = pos[len(key):]
            h = _H_ALIGN.get(rest, "left")
            break
    return v, h


def _overlay_chain(court: Court) -> list[str]:
    """
    Constrói os elementos de overlay de texto/relógio (operam em sysmem).
    Devolve [] se não há texto nem relógio.
    """
    has_text = bool(court.overlay_text and court.overlay_text.strip())
    if not has_text and not court.show_clock:
        return []

    v, h = _split_position(court.overlay_text_position or "BottomLeft")

    # Pango font description: "Família [Bold] [Italic] Tamanho", ex: "DejaVu Sans Bold Italic 36"
    family = court.overlay_font_family or "Sans"
    style = ""
    if getattr(court, "overlay_font_bold", False):
        style += " Bold"
    if getattr(court, "overlay_font_italic", False):
        style += " Italic"
    size = max(8, min(court.overlay_font_size or 24, 120))
    font = f"{family}{style} {size}"
    color = court.overlay_font_color or "white"
    shaded = "true" if getattr(court, "overlay_bg", True) else "false"

    # textoverlay/clockoverlay: cor via 'color' em formato 0xAARRGGBB.
    color_arg = _pango_color(color)

    chain: list[str] = []
    if has_text:
        chain += [
            "textoverlay",
            f"text={court.overlay_text}",
            f"valignment={v}",
            f"halignment={h}",
            f"font-desc={font}",
            f"color={color_arg}",
            f"shaded-background={shaded}",
            "!",
        ]
    if court.show_clock:
        cv = "top" if (has_text and v == "bottom") else v
        chain += [
            "clockoverlay",
            "time-format=%H:%M:%S",
            f"valignment={cv}",
            f"halignment={h}",
            f"font-desc={font}",
            f"color={color_arg}",
            f"shaded-background={shaded}",
            "!",
        ]
    return chain


def _pango_color(c: str) -> str:
    """Converte cor (#RRGGBB ou nome) para 0xAARRGGBB que o textoverlay aceita (color=)."""
    c = (c or "white").strip()
    named = {
        "white": "0xFFFFFFFF", "black": "0xFF000000", "red": "0xFFFF0000",
        "green": "0xFF00FF00", "blue": "0xFF0000FF", "yellow": "0xFFFFFF00",
        "cyan": "0xFF00FFFF", "magenta": "0xFFFF00FF",
    }
    if c.lower() in named:
        return named[c.lower()]
    if c.startswith("#") and len(c) == 7:
        return "0xFF" + c[1:].upper()
    return "0xFFFFFFFF"


def _audio_branch() -> list[str]:
    """
    Ramo de áudio. YouTube exige sempre uma track. Por agora: silêncio sintético.
    (Áudio real da câmara + denoise são um passo posterior, testado no Jetson.)
    """
    return [
        "audiotestsrc", "wave=silence", "is-live=true", "!",
        "audioconvert", "!",
        "voaacenc", "bitrate=128000", "!",
        "aacparse", "!",
        "mux.",
    ]


def build_pipeline_args(court: Court, stream_key: str) -> list[str]:
    """Lista de argumentos para gst-launch-1.0 (sem shell)."""
    w, h = _RESOLUTIONS.get(court.resolution or "1080p", (1920, 1080))
    bitrate_bps = max(1000, court.bitrate_kbps or 4500) * 1000
    fps = court.fps or 25
    iframe = max(1, fps * 2)  # keyframe a cada 2s (requisito YouTube)

    rtsp = build_rtsp_url(court)
    rtmp = f"location={settings.rtmp_base_url.rstrip('/')}/{stream_key} live=1"

    overlay = _overlay_chain(court)

    args: list[str] = [
        settings.gst_launch_bin, "-e",
        # ── entrada RTSP + decode HW ──
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=200", "!",
        "rtph264depay", "!", "h264parse", "!", "nvv4l2decoder", "!",
    ]

    if overlay:
        # Detour para sysmem para os overlays (textoverlay/clockoverlay são CPU),
        # depois volta a NVMM para o encoder.
        args += [
            "nvvidconv", "!", "video/x-raw,format=I420", "!",
            *overlay,
            "nvvidconv", "!",
            f"video/x-raw(memory:NVMM),format=NV12,width={w},height={h}", "!",
        ]
    else:
        # Caminho puro GPU (mais rápido) — sem overlays.
        args += [
            "nvvidconv", "!",
            f"video/x-raw(memory:NVMM),format=NV12,width={w},height={h}", "!",
        ]

    # ── encode NVENC + saída RTMP ──
    args += [
        "nvv4l2h264enc", f"bitrate={bitrate_bps}", "profile=4",
        "insert-sps-pps=1", f"iframeinterval={iframe}", "!",
        "h264parse", "!", "flvmux", "streamable=true", "name=mux", "!",
        "rtmpsink", rtmp,
    ]

    # ── ramo de áudio ──
    args += _audio_branch()
    return args


@dataclass
class StreamState:
    court_id: str
    pid: int = 0
    started_at: Optional[datetime] = None
    last_error: Optional[str] = None
    restart_count: int = 0
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    log_path: Optional[str] = None


class StreamManager:
    """Gere os processos gst-launch por court (start/stop/status)."""

    def __init__(self) -> None:
        self._streams: dict[str, StreamState] = {}
        self._lock = threading.Lock()

    # ─────────────────────────────────────────────────────────────
    def start(self, court: Court) -> StreamState:
        if not court.youtube_stream_key:
            raise ValueError("Stream key não configurada para este court.")

        with self._lock:
            existing = self._streams.get(court.id)
            if existing and existing.process and existing.process.poll() is None:
                return existing  # já a correr

            args = build_pipeline_args(court, court.youtube_stream_key)

            os.makedirs(settings.data_dir, exist_ok=True)
            log_path = os.path.join(settings.data_dir, f"stream_{court.id}.log")
            log_file = open(log_path, "wb")

            # start_new_session=True → o gst fica em grupo de processos próprio,
            # para podermos sinalizar SIGINT só a ele.
            proc = subprocess.Popen(
                args,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            state = StreamState(
                court_id=court.id,
                pid=proc.pid,
                started_at=datetime.utcnow(),
                process=proc,
                log_path=log_path,
                restart_count=existing.restart_count if existing else 0,
            )
            self._streams[court.id] = state
            return state

    # ─────────────────────────────────────────────────────────────
    def stop(self, court_id: str) -> bool:
        with self._lock:
            state = self._streams.get(court_id)
            if not state or not state.process:
                return False
            proc = state.process

        if proc.poll() is None:
            try:
                # SIGINT -> gst-launch -e converte em EOS (finaliza limpo).
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return True

    # ─────────────────────────────────────────────────────────────
    def status(self, court_id: str) -> dict:
        state = self._streams.get(court_id)
        running = bool(state and state.process and state.process.poll() is None)
        last_error = None
        if state and state.process and state.process.poll() not in (None, 0):
            last_error = _tail_log(state.log_path)
        return {
            "court_id": court_id,
            "is_running": running,
            "pid": state.pid if (state and running) else 0,
            "started_at": state.started_at.isoformat() if (state and running and state.started_at) else None,
            "restart_count": state.restart_count if state else 0,
            "last_error": last_error,
        }

    def stop_all(self) -> None:
        for cid in list(self._streams.keys()):
            self.stop(cid)


def _tail_log(path: Optional[str], n: int = 1500) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - n))
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def capture_snapshot(court: Court, run_seconds: int = 4) -> Optional[bytes]:
    """
    Captura um frame da câmara como JPEG (para preview).

    num-buffers=1 não funciona com RTSP (1 pacote RTP != 1 frame; o decoder
    fica à espera). Em vez disso, decodificamos ~run_seconds a 2 fps com
    multifilesink (cada ficheiro é um JPEG completo), paramos, e devolvemos
    o último frame completo. Depois limpamos os temporários.
    """
    rtsp = build_rtsp_url(court)
    os.makedirs(settings.data_dir, exist_ok=True)
    prefix = f"snap_{court.id}_"

    # limpa frames antigos deste court
    for old in glob.glob(os.path.join(settings.data_dir, f"{prefix}*.jpg")):
        try:
            os.remove(old)
        except OSError:
            pass

    out_tmpl = os.path.join(settings.data_dir, f"{prefix}%05d.jpg")
    args = [
        settings.gst_launch_bin,
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=200", "!",
        "rtph264depay", "!", "h264parse", "!", "nvv4l2decoder", "!",
        "nvvidconv", "!", "video/x-raw,format=I420", "!",
        "videorate", "!", "video/x-raw,framerate=2/1", "!",
        "jpegenc", "!", "multifilesink", f"location={out_tmpl}",
    ]

    proc = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
    )
    try:
        proc.wait(timeout=run_seconds)
    except subprocess.TimeoutExpired:
        # mata o grupo de processos (SIGINT -> EOS; depois força se preciso)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGINT)
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    files = sorted(glob.glob(os.path.join(settings.data_dir, f"{prefix}*.jpg")))
    data: Optional[bytes] = None
    # penúltimo = garantidamente completo (o último pode ter sido cortado ao matar)
    chosen = files[-2] if len(files) >= 2 else (files[-1] if files else None)
    if chosen and os.path.getsize(chosen) > 100:
        with open(chosen, "rb") as f:
            data = f.read()

    for old in files:
        try:
            os.remove(old)
        except OSError:
            pass
    return data


# Instância global (singleton) usada pelos endpoints.
manager = StreamManager()
