#!/usr/bin/env python3
"""Captura automática de fotos do tabuleiro de xadrez para calibrar a câmara.

Corre no Jetson. Reutiliza o mesmo pipe gst da análise (o OpenCV do Jetson não
tem GStreamer). Mostra um xadrez à câmara e anda com ele pelo court; sempre que
o detetar, guarda um frame em calib_images/. Pára ao chegar ao alvo (25) ou Ctrl-C.

Uso (no ~/streamingpadel, com o venv da análise):
  CAM_IP=192.168.88.201 CAM_USER=admin CAM_PASSWORD=... \
  analytics-venv/bin/python analytics/calib_capture.py
Opções por ambiente:
  CHESS_COLS, CHESS_ROWS  -> nº de cantos INTERNOS (default 9x6)
  CALIB_TARGET            -> nº de fotos a recolher (default 25)
  CAM_CODEC              -> h264 (default) ou h265
"""
import os
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from heatmap_engine import _gst_cmd, CAP_W, CAP_H  # reusa o pipe da câmara


def _rtsp() -> str:
    ip = os.environ.get("CAM_IP", "")
    if not ip:
        print("ERRO: define CAM_IP (e CAM_USER/CAM_PASSWORD).")
        sys.exit(1)
    u = os.environ.get("CAM_USER", "admin")
    p = os.environ.get("CAM_PASSWORD", "")
    path = os.environ.get("CAM_PATH", "/Streaming/Channels/101")
    return f"rtsp://{u}:{p}@{ip}{path}"


def main() -> int:
    import cv2
    cols = int(os.environ.get("CHESS_COLS", "9"))
    rows = int(os.environ.get("CHESS_ROWS", "6"))
    target = int(os.environ.get("CALIB_TARGET", "25"))
    codec = os.environ.get("CAM_CODEC", "h264")
    pattern = (cols, rows)
    out_dir = os.path.join(HERE, "calib_images")
    os.makedirs(out_dir, exist_ok=True)

    print("Tabuleiro: %dx%d cantos internos | alvo: %d fotos | %dx%d"
          % (cols, rows, target, CAP_W, CAP_H))
    print("Anda com o xadrez pelo court (cantos, centro, perto, longe, inclinado).")
    print("Pasta: %s\n" % out_dir)

    proc = subprocess.Popen(_gst_cmd(_rtsp(), codec, 10), stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=CAP_W * CAP_H * 4)
    frame_bytes = CAP_W * CAP_H * 4
    saved = 0
    last_save = 0.0
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
    try:
        while saved < target:
            buf = proc.stdout.read(frame_bytes)
            if not buf or len(buf) < frame_bytes:
                print("Stream terminou/cortou.")
                break
            frame = np.frombuffer(buf, np.uint8).reshape((CAP_H, CAP_W, 4))[:, :, :3]
            now = time.time()
            if now - last_save < 1.2:          # no máx. ~1 foto/1.2 s
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found, _ = cv2.findChessboardCorners(gray, pattern, flags)
            if found:
                saved += 1
                last_save = now
                fn = os.path.join(out_dir, "chess_%02d.jpg" % saved)
                cv2.imwrite(fn, frame)
                print("  [%2d/%2d] xadrez detetado → %s" % (saved, target, os.path.basename(fn)))
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        try:
            proc.terminate(); proc.wait(timeout=3)
        except Exception:
            proc.kill()
    print("\nGuardadas %d fotos em %s" % (saved, out_dir))
    if saved >= 10:
        print("Agora corre:  analytics-venv/bin/python analytics/calibrate_camera.py")
    else:
        print("Poucas fotos (<10). Repete — garante boa luz e o xadrez bem visível.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
