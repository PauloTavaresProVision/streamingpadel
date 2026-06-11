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

import threading
import time
from typing import List, Optional, Tuple

import numpy as np

# Dimensões do "court endireitado" (vista de cima). Proporção 2:1 (20×10 m).
DST_W, DST_H = 400, 200


def _gst_pipeline(rtsp: str, codec: str) -> str:
    """Pipeline GStreamer para o OpenCV (appsink BGR, decode HW no Jetson)."""
    depay, parse = ("rtph264depay", "h264parse") if codec == "h264" else ("rtph265depay", "h265parse")
    return (
        f"rtspsrc location={rtsp} protocols=tcp latency=300 ! "
        f"{depay} ! {parse} ! nvv4l2decoder ! "
        f"nvvidconv ! video/x-raw,format=BGRx ! "
        f"videoconvert ! video/x-raw,format=BGR ! "
        f"appsink drop=1 max-buffers=1 sync=0"
    )


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
            }

    def reset(self) -> None:
        with self._lock:
            self._acc[:] = 0
            self._frames = 0
            self._detections = 0

    def start(self, rtsp: str, codec_detect, cfg: dict, model_name: str,
              conf: float, fps: float) -> None:
        if self._running:
            return
        corners = cfg.get("court_corners") or []
        if len(corners) != 4:
            raise RuntimeError("Sem calibração: define os 4 cantos do court primeiro.")
        self._cfg = cfg
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

        cap = cv2.VideoCapture(_gst_pipeline(rtsp, codec), cv2.CAP_GSTREAMER)
        if not cap.isOpened() and codec == "h264":
            cap = cv2.VideoCapture(_gst_pipeline(rtsp, "h265"), cv2.CAP_GSTREAMER)
        if not cap.isOpened():
            with self._lock:
                self._error = "Não consegui abrir a câmara (GStreamer)."
                self._running = False
            return

        try:
            self._model = YOLO(model_name)
        except Exception as e:
            cap.release()
            with self._lock:
                self._error = f"Falha a carregar modelo {model_name}: {e}"
                self._running = False
            return

        interval = 1.0 / max(0.2, fps)
        next_t = 0.0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.2)
                continue
            now = time.time()
            if now < next_t:      # respeita o ritmo de amostragem (poupa GPU)
                continue
            next_t = now + interval

            h, w = frame.shape[:2]
            if self._H is None:
                self._H = self._build_homography(corners, w, h)

            try:
                res = self._model.predict(frame, classes=[0], conf=conf, verbose=False)
            except Exception as e:
                with self._lock:
                    self._error = f"Erro na deteção: {e}"
                continue

            boxes = res[0].boxes
            n_inside = 0
            if boxes is not None and len(boxes) > 0:
                import cv2
                xyxy = boxes.xyxy.cpu().numpy()
                # posição dos PÉS = centro inferior da caixa
                feet = np.stack([(xyxy[:, 0] + xyxy[:, 2]) / 2.0, xyxy[:, 3]], axis=1)
                feet = feet.reshape(-1, 1, 2).astype(np.float32)
                proj = cv2.perspectiveTransform(feet, self._H).reshape(-1, 2)
                with self._lock:
                    for (dx, dy) in proj:
                        if 0 <= dx < DST_W and 0 <= dy < DST_H:   # dentro do court
                            self._acc[int(dy), int(dx)] += 1.0
                            n_inside += 1
            with self._lock:
                self._frames += 1
                self._detections += n_inside
                self._current = n_inside

        cap.release()
        with self._lock:
            self._running = False

    # ─────────────────────────── render ───────────────────────────
    def render_png(self) -> Optional[bytes]:
        """Desenha o heatmap (vista de cima) sobre um diagrama do court → PNG."""
        import cv2
        with self._lock:
            acc = self._acc.copy()
        # base: diagrama do court (azul) com linhas
        base = np.full((DST_H, DST_W, 3), (120, 60, 20), dtype=np.uint8)  # BGR azul escuro
        cv2.rectangle(base, (2, 2), (DST_W - 3, DST_H - 3), (255, 255, 255), 1)
        cv2.line(base, (DST_W // 2, 2), (DST_W // 2, DST_H - 2), (255, 255, 255), 1)  # rede
        # linhas de serviço (aprox.: ~25% e ~75% do comprimento)
        for fx in (0.25, 0.75):
            x = int(DST_W * fx)
            cv2.line(base, (x, 2), (x, DST_H - 2), (200, 200, 200), 1)
        cv2.line(base, (2, DST_H // 2), (DST_W - 2, DST_H // 2), (200, 200, 200), 1)

        if acc.max() > 0:
            blur = cv2.GaussianBlur(acc, (0, 0), sigmaX=7, sigmaY=7)
            norm = (blur / blur.max() * 255).astype(np.uint8)
            cmap = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
            mask = (norm > 12).astype(np.float32)[..., None]   # só onde há calor
            out = (base * (1 - 0.65 * mask) + cmap * (0.65 * mask)).astype(np.uint8)
        else:
            out = base

        # ampliar para ficar nítido na página
        out = cv2.resize(out, (DST_W * 2, DST_H * 2), interpolation=cv2.INTER_CUBIC)
        ok, buf = cv2.imencode(".png", out)
        return buf.tobytes() if ok else None


# instância única partilhada pela app
engine = HeatmapEngine()
