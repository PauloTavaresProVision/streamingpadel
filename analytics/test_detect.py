#!/usr/bin/env python3
"""
FASE 0 — teste de viabilidade do heatmap (deteção de jogadores).

Objetivo: confirmar, NO JETSON, se conseguimos detetar os 4 jogadores numa
câmara fixa a ~1-2 fps, e a que custo. NÃO faz heatmap ainda — só deteta,
desenha as caixas e mede a velocidade.

Uso:
    python3 test_detect.py --ip 192.168.88.201 --user admin --password 'P@ssw0rd1535'
    # opções: --seconds 30  --fps 1  --model yolov8n.pt  --conf 0.35

Saída:
    - analytics/out/detect_sample.jpg   (último frame com as caixas verdes)
    - resumo no terminal: nº de pessoas por frame, média, e ms por frame.

Lê o resultado: as caixas apanham bem os 4 jogadores? A que velocidade?
Se sim → avançamos para calibração + heatmap. Se não → ajustamos modelo/conf.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from urllib.parse import quote


def build_rtsp(ip: str, user: str, password: str, path: str) -> str:
    u = quote(user or "", safe="")
    p = quote(password or "", safe="")
    if not path.startswith("/"):
        path = "/" + path
    return f"rtsp://{u}:{p}@{ip}{path}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Fase 0 — teste de deteção de jogadores")
    ap.add_argument("--ip", required=True, help="IP da câmara (ex.: 192.168.88.201)")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", default="")
    ap.add_argument("--path", default="/Streaming/Channels/101", help="caminho RTSP")
    ap.add_argument("--seconds", type=int, default=30, help="duração do teste")
    ap.add_argument("--fps", type=float, default=1.0, help="frames a analisar por segundo")
    ap.add_argument("--model", default="yolov8n.pt", help="modelo YOLO (n=nano, mais leve)")
    ap.add_argument("--conf", type=float, default=0.35, help="confiança mínima")
    args = ap.parse_args()

    try:
        import cv2
        import numpy as np
        from ultralytics import YOLO
    except Exception as e:
        print("ERRO a importar dependências:", e)
        print("Instala primeiro (ver analytics/README.md). torch tem de ser a wheel do JetPack.")
        return 2

    # Diagnóstico de GPU (informativo)
    try:
        import torch
        cuda = torch.cuda.is_available()
        dev = torch.cuda.get_device_name(0) if cuda else "CPU"
        print(f"[gpu] CUDA disponível: {cuda} ({dev})")
        if not cuda:
            print("[gpu] AVISO: a correr em CPU — vai ser lento. Confirma o torch do JetPack.")
    except Exception:
        print("[gpu] torch não encontrado — a deteção pode cair para CPU.")

    rtsp = build_rtsp(args.ip, args.user, args.password, args.path)
    safe = rtsp.replace(args.password, "***") if args.password else rtsp
    print(f"[rtsp] {safe}")

    print(f"[model] a carregar {args.model} … (1ª vez transfere os pesos)")
    model = YOLO(args.model)

    # Abre o stream com FFMPEG/RTSP por TCP (mais estável na LAN).
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
    cap = cv2.VideoCapture(rtsp, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("ERRO: não consegui abrir o stream RTSP. Verifica IP/credenciais/caminho.")
        return 3

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)
    out_img = os.path.join(out_dir, "detect_sample.jpg")

    interval = 1.0 / max(0.1, args.fps)
    end = time.time() + args.seconds
    counts: list[int] = []
    times_ms: list[float] = []
    last = None
    n = 0

    print(f"[run] a analisar ~{args.fps} fps durante {args.seconds}s … (Ctrl+C para parar)")
    try:
        while time.time() < end:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("[run] frame falhou; a tentar reabrir…")
                time.sleep(0.5)
                continue

            t0 = time.time()
            # classes=[0] → só "person". verbose=False para não poluir.
            res = model.predict(frame, classes=[0], conf=args.conf, verbose=False)
            dt = (time.time() - t0) * 1000
            times_ms.append(dt)

            boxes = res[0].boxes
            people = 0 if boxes is None else len(boxes)
            counts.append(people)
            n += 1

            # desenha as caixas no frame (para inspeção visual)
            annotated = res[0].plot()
            cv2.putText(annotated, f"pessoas: {people}  ({dt:.0f} ms)", (12, 32),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            last = annotated

            print(f"  frame {n:3d}: {people} pessoa(s)  {dt:.0f} ms")
            # ritmo alvo
            sleep = interval - (time.time() - t0)
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print("\n[run] interrompido.")
    finally:
        cap.release()

    if last is not None:
        cv2.imwrite(out_img, last)

    print("\n========== RESUMO ==========")
    if counts:
        avg = sum(counts) / len(counts)
        frames4 = sum(1 for c in counts if c >= 4)
        print(f"frames analisados : {len(counts)}")
        print(f"pessoas por frame : média {avg:.1f}  (min {min(counts)}, max {max(counts)})")
        print(f"frames com >=4    : {frames4}/{len(counts)}  "
              f"({100*frames4/len(counts):.0f}%)  <- queremos isto alto")
        print(f"tempo de deteção  : média {sum(times_ms)/len(times_ms):.0f} ms/frame "
              f"(max {max(times_ms):.0f} ms)")
        print(f"imagem de exemplo : {out_img}  <- ABRE ISTO e confirma se apanha os 4 jogadores")
    else:
        print("Nenhum frame analisado — ver erros acima.")
    print("============================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
