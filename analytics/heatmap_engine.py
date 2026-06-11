#!/usr/bin/env python3
"""
Motor do heatmap de jogadores (Fase 2).

Corre numa thread: captura frames da câmara (GStreamer + decode HW), deteta
pessoas (YOLO/ultralytics na GPU), fica só com quem está DENTRO do court
(via homografia dos 4 cantos calibrados), e acumula as posições dos pés num
mapa de calor "visto de cima" (court endireitado 20×10 m).

Desenha-se sobre um diagrama do court. Tudo isolado da app de streaming.
"""
from __future__ import annotations

import subprocess
import threading
import time
from typing import List, Optional, Tuple

import numpy as np

# Dimensões do "court endireitado" (vista de cima). Proporção 2:1 (20×10 m).
DST_W, DST_H = 400, 200

# Resolução a que pedimos os frames ao gst-launch (downscale ajuda a GPU/CPU;
# 1280×720 chega para deteção de pessoas e é mais rápido que 1080p).
CAP_W, CAP_H = 1280, 720


def _gst_cmd(rtsp: str, codec: str) -> list:
    """Comando gst-launch que decodifica o RTSP (HW) e escreve frames BGRx crus
    (4 bytes/pixel) no stdout. O nvvidconv produz BGRx nativamente; o canal alfa
    é descartado no Python. O OpenCV deste Jetson NÃO tem GStreamer, por isso
    lemos os bytes nós próprios — caminho validado no snapshot da calibração."""
    depay, parse = ("rtph264depay", "h264parse") if codec == "h264" else ("rtph265depay", "h265parse")
    return [
        "gst-launch-1.0", "-q",
        "rtspsrc", f"location={rtsp}", "protocols=tcp", "latency=300", "!",
        depay, "!", parse, "!", "nvv4l2decoder", "!",
        "nvvidconv", "!", f"video/x-raw,format=BGRx,width={CAP_W},height={CAP_H}", "!",
        "fdsink", "fd=1", "sync=false",
    ]


class HeatmapEngine:
    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        # acumulador do calor (vista de cima)
        self._acc = np.zeros((DST_H, DST_W), dtype=np.float32)
        self._H = None                 # matriz de homografia (3x3)
        self._running = False
        self._error: Optional[str] = None
        self._frames = 0               # frames analisados
        self._detections = 0           # somatório de jogadores (dentro do court)
        self._current = 0              # jogadores no último frame
        self._started_at = 0.0
        self._model = None
        self._cfg = {}
        # parâmetros afináveis AO VIVO (sem reiniciar a análise)
        self._conf = 0.25          # confiança mínima do YOLO
        self._min_box = 0.012      # altura mín. da caixa (fracção da imagem) — corta reflexos/objetos
        self._max_box = 0.55       # altura máx. — corta blobs gigantes (2 pessoas juntas/sombras)
        self._recent = []          # últimas contagens (para suavizar o KPI)

    # ─────────────────────────── controlo ───────────────────────────
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict:
        with self._lock:
            dur = int(time.time() - self._started_at) if self._running else 0
            return {
                "running": self._running,
                "error": self._error,
                "frames": self._frames,
                "detections": self._detections,
                "current_players": self._current,
                "duration_seconds": dur,
                "has_calibration": bool(self._cfg.get("court_corners")),
                "conf": round(self._conf, 2),
                "min_box": round(self._min_box, 3),
                "max_box": round(self._max_box, 3),
            }

    def set_params(self, conf=None, min_box=None, max_box=None) -> dict:
        """Afina os parâmetros de deteção AO VIVO (aplica no próximo frame)."""
        with self._lock:
            if conf is not None:
                self._conf = max(0.05, min(float(conf), 0.9))
            if min_box is not None:
                self._min_box = max(0.0, min(float(min_box), 0.3))
            if max_box is not None:
                self._max_box = max(0.2, min(float(max_box), 1.0))
        return {"conf": self._conf, "min_box": self._min_box, "max_box": self._max_box}

    def reset(self) -> None:
        with self._lock:
            self._acc[:] = 0
            self._frames = 0
            self._detections = 0
            self._recent = []

    def start(self, rtsp: str, codec_detect, cfg: dict, model_name: str,
              conf: float, fps: float) -> None:
        if self._running:
            return
        corners = cfg.get("court_corners") or []
        if len(corners) != 4:
            raise RuntimeError("Sem calibração: define os 4 cantos do court primeiro.")
        self._cfg = cfg
        self._conf = conf          # valor inicial (depois afinável ao vivo)
        self._stop.clear()
        self._error = None
        self.reset()
        self._thread = threading.Thread(
            target=self._run, name="heatmap-engine", daemon=True,
            args=(rtsp, codec_detect, corners, model_name, conf, fps),
        )
        self._running = True
        self._started_at = time.time()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._running = False

    # ─────────────────────────── loop ───────────────────────────
    def _build_homography(self, corners, frame_w, frame_h):
        import cv2
        # corners em fracções 0..1 → pixels. Ordem: fundo-esq, fundo-dir, frente-dir, frente-esq
        src = np.array([[c[0] * frame_w, c[1] * frame_h] for c in corners], dtype=np.float32)
        dst = np.array([[0, 0], [DST_W, 0], [DST_W, DST_H], [0, DST_H]], dtype=np.float32)
        return cv2.getPerspectiveTransform(src, dst)

    def _run(self, rtsp, codec_detect, corners, model_name, conf, fps) -> None:
        try:
            import cv2
            from ultralytics import YOLO
        except Exception as e:
            with self._lock:
                self._error = f"Falha a importar IA: {e}"
                self._running = False
            return

        # codec da câmara (reusa o detector da app de streaming se disponível)
        codec = "h264"
        try:
            codec = codec_detect(rtsp) or "h264"
        except Exception:
            pass

        try:
            self._model = YOLO(model_name)
        except Exception as e:
            with self._lock:
                self._error = f"Falha a carregar modelo {model_name}: {e}"
                self._running = False
            return

        # arranca o gst-launch a debitar frames BGRx crus (4 bytes/pixel) no stdout
        frame_bytes = CAP_W * CAP_H * 4
        proc = subprocess.Popen(
            _gst_cmd(rtsp, codec), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=frame_bytes,
        )
        if self._H is None:
            self._H = self._build_homography(corners, CAP_W, CAP_H)

        interval = 1.0 / max(0.2, fps)
        next_t = 0.0
        try:
            while not self._stop.is_set():
                # lê exatamente 1 frame do stdout
                buf = proc.stdout.read(frame_bytes)
                if not buf or len(buf) < frame_bytes:
                    # processo morreu/stream caiu → tenta de novo
                    with self._lock:
                        self._error = "Stream interrompido; a recuperar…"
                    break
                now = time.time()
                if now < next_t:      # ritmo de amostragem (poupa GPU) — descarta frame
                    continue
                next_t = now + interval

                # BGRx → descarta o canal alfa (4º) → BGR para o YOLO
                frame = np.frombuffer(buf, dtype=np.uint8).reshape((CAP_H, CAP_W, 4))[:, :, :3]

                try:
                    res = self._model.predict(frame, classes=[0], conf=self._conf, verbose=False)
                except Exception as e:
                    with self._lock:
                        self._error = f"Erro na deteção: {e}"
                    continue

                boxes = res[0].boxes
                n_inside = 0
                if boxes is not None and len(boxes) > 0:
                    xyxy = boxes.xyxy.cpu().numpy()
                    # filtro por TAMANHO da caixa: descarta deteções minúsculas
                    # (reflexos/objetos) e gigantes (2 pessoas juntas/sombras).
                    bh = (xyxy[:, 3] - xyxy[:, 1]) / CAP_H        # altura em fracção
                    keep = (bh >= self._min_box) & (bh <= self._max_box)
                    xyxy = xyxy[keep]
                    if len(xyxy) > 0:
                        # posição dos PÉS = centro inferior da caixa
                        feet = np.stack([(xyxy[:, 0] + xyxy[:, 2]) / 2.0, xyxy[:, 3]], axis=1)
                        feet = feet.reshape(-1, 1, 2).astype(np.float32)
                        proj = cv2.perspectiveTransform(feet, self._H).reshape(-1, 2)
                        # margem de tolerância: quem cai um pouco fora (perspetiva/
                        # fisheye na frente) conta na BORDA mais próxima; quem está
                        # muito fora (café/staff/2º court) é ignorado.
                        MX, MY = DST_W * 0.10, DST_H * 0.10
                        with self._lock:
                            for (dx, dy) in proj:
                                if -MX <= dx < DST_W + MX and -MY <= dy < DST_H + MY:
                                    cx = int(min(DST_W - 1, max(0, dx)))
                                    cy = int(min(DST_H - 1, max(0, dy)))
                                    self._acc[cy, cx] += 1.0
                                    n_inside += 1
                with self._lock:
                    self._frames += 1
                    self._detections += n_inside
                    # KPI suavizado: mediana das últimas 5 leituras (estabiliza o
                    # número quando salta entre 2/4/5 por frame).
                    self._recent.append(n_inside)
                    if len(self._recent) > 5:
                        self._recent.pop(0)
                    s = sorted(self._recent)
                    self._current = s[len(s) // 2]
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        with self._lock:
            self._running = False

    # ─────────────────────────── render ───────────────────────────
    def _court_base(self, w: int, h: int):
        """Imagem de fundo do court. Se existir analytics/court_bg.(png|jpg) usa-a
        (a imagem que o utilizador forneceu, vista de cima); senão desenha um
        diagrama 2D simples."""
        import os
        import cv2
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("court_bg.png", "court_bg.jpg", "court_bg.jpeg"):
            p = os.path.join(here, name)
            if os.path.exists(p):
                img = cv2.imread(p, cv2.IMREAD_COLOR)
                if img is not None:
                    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
        # fallback: diagrama desenhado
        base = np.full((h, w, 3), (120, 60, 20), dtype=np.uint8)   # BGR azul
        cv2.rectangle(base, (2, 2), (w - 3, h - 3), (255, 255, 255), 1)
        cv2.line(base, (w // 2, 2), (w // 2, h - 2), (255, 255, 255), 1)
        for fx in (0.25, 0.75):
            x = int(w * fx)
            cv2.line(base, (x, 2), (x, h - 2), (200, 200, 200), 1)
        cv2.line(base, (2, h // 2), (w - 2, h // 2), (200, 200, 200), 1)
        return base

    def render_png(self) -> Optional[bytes]:
        """Sobrepõe o heatmap (vista de cima) à imagem de fundo do court → PNG."""
        import cv2
        with self._lock:
            acc = self._acc.copy()
        OUT_W, OUT_H = DST_W * 3, DST_H * 3          # render final mais nítido
        base = self._court_base(OUT_W, OUT_H)

        # Sub-região da imagem de fundo onde está o court azul (fracções 0..1).
        # O heatmap (retângulo perfeito) é colocado SÓ aqui, para não pintar a
        # faixa cinzenta/paredes da imagem. Ajustável via court_area na config.
        area = (self._cfg.get("court_area") or {})
        ax0 = int(OUT_W * float(area.get("left", 0.0)))
        ax1 = int(OUT_W * float(area.get("right", 1.0)))
        ay0 = int(OUT_H * float(area.get("top", 0.0)))
        ay1 = int(OUT_H * float(area.get("bottom", 1.0)))
        aw, ah = max(1, ax1 - ax0), max(1, ay1 - ay0)

        if acc.max() > 0:
            heat = cv2.resize(acc, (aw, ah), interpolation=cv2.INTER_LINEAR)
            # blur menor → focos definidos (estilo "manchas", não borrão suave)
            blur = cv2.GaussianBlur(heat, (0, 0), sigmaX=7, sigmaY=7)
            n = blur / blur.max()
            # realça os picos: gamma<1 puxa o calor médio para cima → núcleos
            # vermelhos bem marcados como na referência
            n = np.power(n, 0.7)
            norm = (n * 255).astype(np.uint8)
            cmap = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
            # alfa: transparente onde não há calor; opaco e vivo onde há
            a = np.where(norm > 18, np.clip(0.30 + n * 0.62, 0, 0.92), 0.0)
            a = a.astype(np.float32)[..., None]
            roi = base[ay0:ay1, ax0:ax1]
            base[ay0:ay1, ax0:ax1] = (roi * (1 - a) + cmap * a).astype(np.uint8)
        out = base

        ok, buf = cv2.imencode(".png", out)
        return buf.tobytes() if ok else None


# instância única partilhada pela app
engine = HeatmapEngine()
