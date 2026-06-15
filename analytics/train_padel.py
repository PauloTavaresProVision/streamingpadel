#!/usr/bin/env python3
"""Treina (fine-tune) um detetor de padel com YOLOv8. CORRER NUMA GPU (Colab/
Kaggle/RunPod), NÃO no Jetson. Produz best.pt — depois copias para o Jetson e
exportas a engine LÁ (a .engine é específica do GPU, não é portável).

Passos na cloud:
  pip install ultralytics
  python train_padel.py --data /caminho/data.yaml --epochs 80
Resultado: runs/detect/padel/weights/best.pt

Se faltar memória de GPU (OOM): baixa --batch (ex.: 4 ou 2) ou --imgsz 960.
"""
import argparse


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="data.yaml exportado do Roboflow (YOLOv8)")
    ap.add_argument("--base", default="yolov8s.pt", help="modelo base p/ fine-tune")
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--imgsz", type=int, default=1280, help="igual à inferência no Jetson")
    ap.add_argument("--batch", type=int, default=4, help="baixa se faltar VRAM (OOM)")
    a = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(a.base)
    model.train(
        data=a.data, epochs=a.epochs, imgsz=a.imgsz, batch=a.batch,
        patience=20,                 # pára cedo se não melhorar
        degrees=0.0,                 # vista cenital fixa → SEM rotação
        fliplr=0.5,                  # espelho horizontal ajuda (court ~simétrico)
        mosaic=1.0, scale=0.5,       # variedade de escala (jogadores perto/longe)
        name="padel",
    )
    print("\n== Treino terminado ==")
    print("Pesos: runs/detect/padel/weights/best.pt")
    print("Avalia em runs/detect/padel/ (curvas, matriz de confusão, val preds).")
    print("\nDeploy no Jetson:")
    print("  1) copia best.pt → ~/streamingpadel/yolov8s.pt (substitui)")
    print("  2) rm -f ~/streamingpadel/yolov8s.engine")
    print("  3) ~/analytics-venv/bin/python analytics/export_tensorrt.py")
    print("  4) sudo systemctl restart padel-analytics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
