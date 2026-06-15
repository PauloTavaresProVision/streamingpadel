# Treinar o modelo de padel — guia completo

Objetivo: substituir o YOLO genérico (que falha jogadores agachados/na rede e
baralha IDs) por um modelo **treinado em padel**, que deteta jogadores em
**qualquer pose** e do **nosso ângulo cenital**. Resolve a deteção; é também a
base para a bola.

Resumo do fluxo: **extrair frames → anotar → treinar (cloud) → exportar →
deploy no Jetson.** GPU só para o treino (cloud, ~5 €); o resto é no PC/browser.

---

## 1. Extrair frames (com pré-anotação automática)
No Jetson, sobre a última gravação analisada:
```bash
~/analytics-venv/bin/python analytics/extract_frames.py --every 3
```
- Gera ~300 frames (1 a cada 3 s) em `analytics/out/dataset_raw/`, cada um com um
  `.txt` **já com os jogadores pré-marcados** (auto-label + filtro do court).
- Copia essa pasta para o teu PC (ex.: `scp` ou pela pasta pública `data/`).

## 2. Anotar (corrigir) — Roboflow (grátis)
1. Cria conta em roboflow.com → novo projeto **Object Detection**, classe única `jogador`.
2. Faz **upload** da pasta `dataset_raw` (importa imagens + os `.txt` YOLO).
3. Revê cada frame e **corrige**: adiciona os jogadores que faltam (agachados, na
   rede, tapados), apaga caixas erradas, ajusta caixas largas. Caixa = **dos pés à
   cabeça, justa**.
4. **Generate** → **Export** em formato **YOLOv8** → dá-te `data.yaml + images/ + labels/`.

### Princípios para uma base sólida
- **Variedade > quantidade**: 300 frames variados > 2000 iguais. Mete momentos
  com jogadores em pé, agachados, no afundo, na rede, a cruzarem-se, luz diferente.
- **Inclui de propósito os casos que falham hoje** (agachado/na rede) — é o que
  ensina o modelo a vê-los.
- **Consistência**: a caixa sempre igual (pés→cabeça, justa). Anotação
  inconsistente piora o treino.
- **Split**: ~85% train / 15% val (o Roboflow faz automático).

## 3. Treinar (na cloud — Kaggle grátis ou RunPod ~5 €)
Sobe o dataset exportado e corre:
```bash
pip install ultralytics
python train_padel.py --data /caminho/data.yaml --epochs 80
```
- `imgsz=1280` por omissão (igual à inferência no Jetson). Se faltar memória
  (OOM): `--batch 2` ou `--imgsz 960`.
- Resultado: `runs/detect/padel/weights/best.pt`. Vê as curvas e as previsões de
  validação em `runs/detect/padel/` para confirmar que ficou bom.
- Faz **download** do `best.pt`.

## 4. Deploy no Jetson
```bash
# copia best.pt para o Jetson como o modelo usado:
cp best.pt ~/streamingpadel/yolov8s.pt          # substitui o genérico
rm -f ~/streamingpadel/yolov8s.engine           # a engine antiga e do modelo antigo
~/analytics-venv/bin/python analytics/export_tensorrt.py   # nova engine (~12 min)
sudo systemctl restart padel-analytics
```
(A engine TENSORRT tem de ser gerada NO Jetson — não copies a engine da cloud.)

## 5. Validar
Re-analisa a gravação + 👁 Ver tracking. Deves ver os 4 jogadores detetados de
forma muito mais consistente, incluindo agachados e na rede.

---

## Fase 2 (depois): a bola
A bola anota-se igual (caixinha à volta dela, frame a frame — dá mais trabalho).
Ver [BALL_MODULE.md](BALL_MODULE.md) — TrackNetV2 + dataset PadelTracker100. É um
modelo separado (a bola é pequena/rápida demais para o detetor de jogadores).

## Custos e tempo (realista)
- GPU: Kaggle grátis (30h/sem) OU RunPod ~0,4 €/h × 3-4 h = **~2-5 €**.
- O teu tempo: **anotar** ~300 frames corrigindo o auto-label = ~1-2 h na 1ª vez.
- Treino: 2-4 h (corre sozinho).
- O resultado vale a pena: é o que tira o sistema de "razoável" para "fiável".
