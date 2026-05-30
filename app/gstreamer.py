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
import socket
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


_codec_cache: dict[str, str] = {}


def _detect_codec(rtsp: str) -> str:
    """Descobre o codec de vídeo da câmara (h264/h265) via gst-discoverer. Cacheado."""
    if rtsp in _codec_cache:
        return _codec_cache[rtsp]
    codec = "h264"
    try:
        out = subprocess.run(
            ["gst-discoverer-1.0", rtsp],
            capture_output=True, text=True, timeout=15,
        )
        blob = (out.stdout + out.stderr).lower()
        if "h.265" in blob or "h265" in blob or "hevc" in blob:
            codec = "h265"
    except Exception:
        pass
    _codec_cache[rtsp] = codec
    return codec


def _depay_parse(codec: str) -> list[str]:
    """Elementos de depay+parse conforme o codec. nvv4l2decoder (HW) decoda ambos."""
    if codec == "h265":
        return ["rtph265depay", "!", "h265parse", "!"]
    return ["rtph264depay", "!", "h264parse", "!"]


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


def _parse_pos(pos: str, default: tuple[float, float]) -> tuple[float, float]:
    """Posição -> fracções (0..1). Aceita 'x,y' em % ou presets."""
    if pos and "," in pos:
        try:
            x, y = pos.split(",")
            return max(0.0, min(1.0, float(x) / 100)), max(0.0, min(1.0, float(y) / 100))
        except Exception:
            pass
    # Tabela CANÓNICA de presets (igual no editor e no preview).
    presets = {
        "TopLeft": (0.03, 0.04), "TopCenter": (0.40, 0.04), "TopRight": (0.80, 0.04),
        "BottomLeft": (0.03, 0.86), "BottomCenter": (0.40, 0.86), "BottomRight": (0.80, 0.86),
    }
    return presets.get(pos or "", default)


def _font_desc(court: Court, out_h: int = 1080) -> str:
    family = court.overlay_font_family or "Sans"
    style = ""
    if getattr(court, "overlay_font_bold", False):
        style += " Bold"
    if getattr(court, "overlay_font_italic", False):
        style += " Italic"
    px = max(8, min(court.overlay_font_size or 24, 200))
    # px do editor é relativo a 1080p → escala para a resolução real.
    px = px * (out_h / 1080.0)
    # Pango usa PONTOS. Com auto-resize=false, pt × 96/72 = px. pt = px × 0.75.
    pt = max(6, round(px * 0.75))
    return f"{family}{style} {pt}"


def _anchor(pos: str, default: str) -> tuple[str, str]:
    """Mapeia posição (preset ou 'x,y' %) para (halignment, valignment) fiáveis."""
    x, y = _parse_pos(pos or default, (0.03, 0.04))
    h = "left" if x < 0.34 else ("center" if x < 0.66 else "right")
    v = "top" if y < 0.5 else "bottom"
    return h, v


def _txt_element(name: str, props: dict) -> list[str]:
    """Constrói um elemento de overlay de texto com posicionamento por fracção."""
    out = [name]
    for k, v in props.items():
        out.append(f"{k}={v}")
    out.append("!")
    return out


def _overlay_chain(court: Court, w: int, h: int) -> list[str]:
    """
    Overlays em sysmem (texto, relógio, cronómetro). Posição EXACTA: âncora
    top-left + xpad/ypad em pixels = (x%·W, y%·H) → cada elemento fica onde foi
    arrastado no editor. Cor, fonte (bold/italic/px) e caixa sombreada.
    """
    has_text = bool(court.show_text and court.overlay_text and court.overlay_text.strip())
    show_clock = bool(court.show_clock)
    show_timer = bool(getattr(court, "show_timer", False))
    if not (has_text or show_clock or show_timer):
        return []

    font = _font_desc(court, h)
    chain: list[str] = []

    def pads(pos: str, default: str) -> tuple[int, int]:
        fx, fy = _parse_pos(pos or default, (0.03, 0.04))
        return round(fx * w), round(fy * h)

    if has_text:
        px, py = pads(court.overlay_text_position or "BottomLeft", "BottomLeft")
        chain += _txt_element("textoverlay", {
            "text": f'"{court.overlay_text}"',
            "halignment": "left", "valignment": "top", "xpad": str(px), "ypad": str(py),
            "wrap-mode": "none",        # nunca quebrar linha (igual ao preview)
            "auto-resize": "false",     # tamanho fixo (sem isto ignora o font-desc)
            "font-desc": f'"{font}"',
            "color": _pango_color(court.overlay_font_color or "white"),
            "shaded-background": "true" if getattr(court, "overlay_bg", True) else "false",
            "shading-value": "140",
        })

    if show_clock:
        px, py = pads(getattr(court, "clock_position", "TopRight") or "TopRight", "TopRight")
        fmt = "%I:%M" if getattr(court, "clock_format", "24h") == "12h" else "%H:%M"
        chain += _txt_element("clockoverlay", {
            "time-format": f'"{fmt}:%S"',
            "halignment": "left", "valignment": "top", "xpad": str(px), "ypad": str(py),
            "wrap-mode": "none", "auto-resize": "false",
            "font-desc": f'"{font}"',
            "color": _pango_color(getattr(court, "clock_color", "#FFFFFF") or "#FFFFFF"),
            "shaded-background": "true", "shading-value": "140",
        })

    if show_timer:
        px, py = pads(getattr(court, "timer_position", "BottomLeft") or "BottomLeft", "BottomLeft")
        chain += _txt_element("timeoverlay", {
            "time-mode": "buffer-time",
            "halignment": "left", "valignment": "top", "xpad": str(px), "ypad": str(py),
            "wrap-mode": "none", "auto-resize": "false",
            "font-desc": f'"{font}"',
            "color": _pango_color(getattr(court, "timer_color", "#FFFFFF") or "#FFFFFF"),
            "shaded-background": "true", "shading-value": "140",
        })

    return chain


def _crop_scale_chain(court: Court, w: int, h: int) -> list[str]:
    """
    Crop+zoom: normaliza a fonte a WxH, recorta a região (% sobre WxH) e re-escala
    a WxH (= efeito de zoom). Devolve elementos sysmem. Se não há crop, só normaliza.
    """
    region = (court.crop_region or "").split(",")
    # Sem crop: normaliza a fonte a WxH na GPU (nvvidconv) e entrega em sysmem
    # I420 para os overlays. interpolation-method=1 (Bilinear) — o default é
    # "Nearest" (0), que serrilha ao reduzir 1440p/4MP→1080p (qualidade fraca).
    base = ["nvvidconv", "interpolation-method=1", "!",
            f"video/x-raw,format=I420,width={w},height={h}", "!"]
    if len(region) == 4:
        try:
            x, y, cw, ch = (float(v) for v in region)
            if not (x <= 0.5 and y <= 0.5 and cw >= 99.5 and ch >= 99.5):
                left = round(x / 100 * w)
                top = round(y / 100 * h)
                right = round((100 - x - cw) / 100 * w)
                bottom = round((100 - y - ch) / 100 * h)
                left = max(0, left); top = max(0, top); right = max(0, right); bottom = max(0, bottom)
                # videocrop selecciona a região; videoscale (software) re-escala a
                # WxH (= zoom). NOTA: o caminho GPU (nvvidconv sysmem→NVMM→sysmem)
                # produzia frames verdes no Jetson — por isso fica em software.
                return base + [
                    "videocrop", f"left={left}", f"right={right}", f"top={top}", f"bottom={bottom}", "!",
                    "videoscale", "!", f"video/x-raw,width={w},height={h}", "!",
                ]
        except Exception:
            pass
    return base


def _image_size(path: str) -> tuple[int, int]:
    """Dimensões da imagem (w,h). Fallback (1,1) se não conseguir ler."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (1, 1)


def _logo_element(court: Court, content_root: str, w: int, h: int) -> list[str]:
    """gdkpixbufoverlay com o logo, posicionado por fracção e dimensionado em % da largura,
    mantendo a proporção (calcula overlay-height a partir das dimensões reais)."""
    if not (getattr(court, "show_logo", True) and court.logo_path):
        return []
    path = os.path.join(content_root, "data", court.logo_path)
    if not os.path.exists(path):
        return []
    x, y = _parse_pos(court.logo_position or "TopRight", (0.78, 0.04))
    size_pct = max(3, min(court.logo_size_percent or 10, 40))
    ow = round(size_pct / 100 * w)
    iw, ih = _image_size(path)
    oh = round(ow * ih / iw) if iw > 0 else ow   # mantém proporção
    alpha = max(0.1, min((court.logo_opacity or 100) / 100, 1.0))
    # offset em pixels (relative-x/y às vezes ignora overlay-width; usamos offset absoluto)
    off_x = round(x * w)
    off_y = round(y * h)
    return [
        "gdkpixbufoverlay", f"location={path}",
        f"offset-x={off_x}", f"offset-y={off_y}",
        f"overlay-width={ow}", f"overlay-height={oh}",
        f"alpha={alpha:.2f}", "!",
    ]


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
    # Padel = muito movimento → bitrate baixo "esborrata". Piso por resolução
    # (mesmo que a court tenha um valor antigo baixo guardado, sobe-se ao mínimo).
    floor_kbps = 6000 if w >= 1920 else 3500
    bitrate_bps = max(court.bitrate_kbps or 8000, floor_kbps) * 1000
    fps = court.fps or 25
    iframe = max(1, fps * 2)  # keyframe a cada 2s (requisito YouTube)

    rtsp = build_rtsp_url(court)
    rtmp = f"location={settings.rtmp_base_url.rstrip('/')}/{stream_key} live=1"

    content_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    crop_scale = _crop_scale_chain(court, w, h)   # nvvidconv→I420 WxH (+crop+rescale)
    overlay = _overlay_chain(court, w, h)         # texto/relógio/cronómetro (sysmem)
    logo = _logo_element(court, content_root, w, h)  # gdkpixbufoverlay (sysmem)

    codec = _detect_codec(rtsp)
    args: list[str] = [
        settings.gst_launch_bin, "-e",
        # ── entrada RTSP + decode HW (codec detectado: h264/h265) ──
        # latency=500: jitter-buffer maior. Com bitrate alto na câmara os frames
        # são maiores e chegam com mais variação na rede; 200 ms era curto e
        # causava "abanar" (frames mostrados fora de tempo). YouTube já tem o seu
        # próprio buffer, por isso +300 ms aqui não se nota no espectador.
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=500", "!",
        *_depay_parse(codec),
        # queue desacopla a rede do decoder: absorve rajadas sem travar o encoder.
        "queue", "max-size-time=2000000000", "max-size-bytes=0", "max-size-buffers=0", "!",
        "nvv4l2decoder", "!",
    ]

    # Pipeline em sysmem: crop/zoom → texto/relógio/cronómetro → logo → volta a NVMM
    args += crop_scale
    args += overlay
    args += logo
    args += [
        "nvvidconv", "!",
        f"video/x-raw(memory:NVMM),format=NV12,width={w},height={h}", "!",
    ]

    # ── encode NVENC + saída RTMP ──
    # Config VALIDADA (confirmada "sem cortes"). NÃO adicionar flags
    # especulativas (control-rate/peak-bitrate/idrinterval introduziram abanar).
    # maxperf-enable=1 é seguro: mantém o encoder à frequência máxima.
    args += [
        "nvv4l2h264enc", f"bitrate={bitrate_bps}", "profile=4",
        "maxperf-enable=1", "insert-sps-pps=1", f"iframeinterval={iframe}", "!",
        "h264parse", "!",
        # queue antes do mux/rtmpsink: a saída de rede não trava o encoder.
        "queue", "max-size-time=2000000000", "max-size-bytes=0", "max-size-buffers=0", "!",
        "flvmux", "streamable=true", "name=mux", "!",
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
            # Regista o comando completo no topo do log (para diagnóstico).
            try:
                log_file.write(("CMD: " + " ".join(args) + "\n\n").encode("utf-8"))
                log_file.flush()
            except Exception:
                pass

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

    codec = _detect_codec(rtsp)
    out_tmpl = os.path.join(settings.data_dir, f"{prefix}%05d.jpg")
    args = [
        settings.gst_launch_bin,
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=200", "!",
        *_depay_parse(codec), "nvv4l2decoder", "!",
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
        # guarda como cache estável deste court (servido sem re-capturar)
        try:
            cache = _snapshot_cache_path(court.id)
            os.makedirs(os.path.dirname(cache), exist_ok=True)
            with open(cache, "wb") as f:
                f.write(data)
        except OSError:
            pass

    for old in files:
        try:
            os.remove(old)
        except OSError:
            pass
    return data


def _snapshot_cache_path(court_id: str) -> str:
    return os.path.join(settings.data_dir, "snapshots", f"court_{court_id}.jpg")


def get_snapshot(court: Court, ttl: int = 300, force: bool = False) -> Optional[bytes]:
    """Devolve o snapshot em cache se fresco (< ttl s); senão captura de novo."""
    cache = _snapshot_cache_path(court.id)
    if not force and os.path.exists(cache) and os.path.getsize(cache) > 100:
        if (time.time() - os.path.getmtime(cache)) < ttl:
            with open(cache, "rb") as f:
                return f.read()
    return capture_snapshot(court)


def camera_online(ip: str, port: int = 554, timeout: float = 1.5) -> bool:
    """Câmara acessível? TCP connect à porta RTSP (554)."""
    if not ip:
        return False
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


# Instância global (singleton) usada pelos endpoints.
manager = StreamManager()
