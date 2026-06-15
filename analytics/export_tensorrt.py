#!/usr/bin/env python3
"""Exporta o modelo YOLO para TensorRT (.engine) — inferência ~3x mais rápida no
Jetson (validado no Orin NX: ~13,9 ms → ~4,1 ms por frame, FP16). A análise passa
a usar a .engine automaticamente se ela existir ao lado do .pt.

IMPORTANTE: corre UMA vez NO JETSON — a .engine é compilada para AQUELE GPU/versão
de TensorRT (não é portável entre máquinas). Demora alguns minutos.

Uso (no ~/streamingpadel, com o venv da análise):
  analytics-venv/bin/python analytics/export_tensorrt.py            # yolov8s.pt
  analytics-venv/bin/python analytics/export_tensorrt.py yolov8n.pt # outro modelo
Depois: sudo systemctl restart padel-analytics
"""
import sys


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "yolov8s.pt"
    try:
        from ultralytics import YOLO
    except Exception as e:
        print("Falta o ultralytics no venv da análise:", e)
        return 1
    print("A exportar %s → TensorRT FP16 @ 1280. Pode demorar vários minutos..." % model)
    try:
        # half=True (FP16): bom equilíbrio velocidade/precisão no Jetson.
        # imgsz=1280: TEM de bater com INFER_IMGSZ do motor (deteta melhor os
        # jogadores pequenos/tapados pela rede que a 640 desapareciam).
        YOLO(model).export(format="engine", half=True, device=0, imgsz=1280)
    except Exception as e:
        print("Falha na exportação:", e)
        print("Verifica: GPU disponível, espaço em disco e que o .pt existe/baixa.")
        return 1
    eng = model.rsplit(".", 1)[0] + ".engine"
    print("\nFeito → %s" % eng)
    print("A análise vai usá-la automaticamente. Reinicia:")
    print("  sudo systemctl restart padel-analytics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
