#!/usr/bin/env python3
"""Extrai frames de uma gravação E pré-marca os jogadores (auto-label) com o
modelo atual — para acelerar a anotação. Saída em formato YOLO (jpg + txt ao
lado), pronta a importar no Roboflow/CVAT, onde só CORRIGES (adicionas os
agachados/tapados que o modelo falhou, apagas estranhos).

Corre NO JETSON (venv da análise), usa o mesmo pipe gst da análise:
  ~/analytics-venv/bin/python analytics/extract_frames.py --every 3
Opções:
  video (1º arg)  default out/videos/analyze.mp4 (a última gravação analisada)
  --every N       segundos entre frames extraídos (default 3 → ~300 p/ 15 min)
  --conf C        confiança do auto-label (default 0.25)
"""
import argparse
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from heatmap_engine import _gst_file_cmd, CAP_W, CAP_H   # pipe de leitura fiável


def _in_poly(px, py, poly):
    """Ponto dentro do court (ray casting). poly em píxeis."""
    n, inside, j = len(poly), False, len(poly) - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / ((yj - yi) or 1e-9) + xi):
            inside = not inside
        j = i
    return inside


def main() -> int:
    import cv2
    import json
    from ultralytics import YOLO

    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?",
                    default=os.path.join(HERE, "out", "videos", "analyze.mp4"))
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--model", default="yolov8s.pt")
    a = ap.parse_args()
    if not os.path.exists(a.video):
        print("Vídeo não encontrado:", a.video)
        return 1

    out = os.path.join(HERE, "out", "dataset_raw")
    os.makedirs(out, exist_ok=True)
    # polígono do court (frações) p/ manter só jogadores dentro do campo
    poly_fr = None
    try:
        cc = json.load(open(os.path.join(HERE, "config.json"))).get("court_corners")
        if cc and len(cc) == 4:
            poly_fr = cc
    except Exception:
        pass

    model = YOLO(a.model)
    # lê a 2 fps e guarda 1 a cada `every` s (subamostragem)
    read_fps = 2.0
    keep = max(1, int(round(read_fps * a.every)))
    proc = subprocess.Popen(_gst_file_cmd(a.video, int(read_fps)),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            bufsize=CAP_W * CAP_H * 4)
    fb = CAP_W * CAP_H * 4
    poly_px = [(p[0] * CAP_W, p[1] * CAP_H) for p in poly_fr] if poly_fr else None
    i, saved = -1, 0
    try:
        while True:
            buf = proc.stdout.read(fb)
            if not buf or len(buf) < fb:
                break
            i += 1
            if i % keep != 0:
                continue
            frame = np.frombuffer(buf, np.uint8).reshape((CAP_H, CAP_W, 4))[:, :, :3].copy()
            res = model.predict(frame, classes=[0], conf=a.conf, imgsz=1280, verbose=False)
            lines = []
            b = res[0].boxes
            if b is not None and len(b) > 0:
                for x1, y1, x2, y2 in b.xyxy.cpu().numpy():
                    fxp, fyp = (x1 + x2) / 2.0, y2          # pés
                    if poly_px and not _in_poly(fxp, fyp, poly_px):
                        continue
                    cxn = ((x1 + x2) / 2.0) / CAP_W
                    cyn = ((y1 + y2) / 2.0) / CAP_H
                    wn, hn = (x2 - x1) / CAP_W, (y2 - y1) / CAP_H
                    lines.append("0 %.6f %.6f %.6f %.6f" % (cxn, cyn, wn, hn))
            name = "frame_%05d" % saved
            cv2.imwrite(os.path.join(out, name + ".jpg"), frame)
            with open(os.path.join(out, name + ".txt"), "w") as f:
                f.write("\n".join(lines))
            saved += 1
            if saved % 25 == 0:
                print("...", saved, "frames")
    finally:
        try:
            proc.terminate(); proc.wait(timeout=3)
        except Exception:
            proc.kill()
    print("\nFeito: %d frames + pré-anotações em %s" % (saved, out))
    print("Copia essa pasta para o teu PC, importa no Roboflow (YOLOv8),")
    print("CORRIGE (agachados/na rede que faltam, apaga estranhos) e exporta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
