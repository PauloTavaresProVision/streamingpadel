#!/usr/bin/env python3
"""Calcula a calibração da câmara a partir das fotos do xadrez (calib_images/).

Deteta os cantos do tabuleiro em cada foto, corre cv2.calibrateCamera (modelo
radial-tangencial padrão) e grava camera_calib.json (matriz K + coeficientes de
distorção + erro de reprojeção). O motor do heatmap usa esse ficheiro, se existir,
para corrigir a lente com precisão (em vez do k1/k2 afinado à mão).

Uso (no ~/streamingpadel, com o venv da análise):
  analytics-venv/bin/python analytics/calibrate_camera.py
Opções por ambiente: CHESS_COLS, CHESS_ROWS (cantos internos, default 9x6).
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "camera_calib.json")


def main() -> int:
    import cv2
    cols = int(os.environ.get("CHESS_COLS", "9"))
    rows = int(os.environ.get("CHESS_ROWS", "6"))
    pattern = (cols, rows)
    imgs = sorted(glob.glob(os.path.join(HERE, "calib_images", "*.jpg")))
    if len(imgs) < 6:
        print("Poucas fotos em calib_images/ (%d). Corre antes o calib_capture.py." % len(imgs))
        return 1

    # pontos 3D do tabuleiro (z=0). A escala (quadrado) não afeta a distorção.
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE

    objpoints, imgpoints, size, used = [], [], None, 0
    for fn in imgs:
        img = cv2.imread(fn)
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        size = (gray.shape[1], gray.shape[0])
        found, corners = cv2.findChessboardCorners(gray, pattern, flags)
        if not found:
            print("  ignorada (sem xadrez): %s" % os.path.basename(fn))
            continue
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        objpoints.append(objp)
        imgpoints.append(corners)
        used += 1

    if used < 6:
        print("Só %d fotos com xadrez detetado — preciso de >=6 (ideal 15+)." % used)
        return 1

    rms, K, dist, _, _ = cv2.calibrateCamera(objpoints, imgpoints, size, None, None)
    data = {
        "model": "standard",
        "image_size": [size[0], size[1]],
        "K": K.tolist(),
        "dist": np.ravel(dist).tolist(),
        "rms": float(rms),
        "n_images": used,
    }
    with open(OUT_JSON, "w") as f:
        json.dump(data, f, indent=2)

    print("\n== Calibração concluída ==")
    print("  fotos usadas:        %d" % used)
    print("  erro de reprojeção:  %.3f px  (<1.0 = bom, <0.5 = excelente)" % rms)
    print("  matriz K:\n%s" % np.array2string(K, precision=1))
    print("  distorção:           %s" % np.array2string(np.ravel(dist), precision=4))
    print("\n  Gravado em %s" % OUT_JSON)
    print("  Reinicia a análise (sudo systemctl restart padel-analytics) para passar a usar.")
    if rms > 1.5:
        print("\n  ATENÇÃO: erro alto (>1.5 px). Tira mais fotos, com o xadrez")
        print("  bem nítido e a cobrir também os CANTOS do enquadramento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
