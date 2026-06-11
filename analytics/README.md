# Análise de jogo — Heatmap de jogadores (Fase 0: teste de viabilidade)

Esta pasta é **independente** da app de streaming. O objetivo da Fase 0 é
confirmar, no Jetson, se conseguimos detetar os 4 jogadores de uma câmara fixa
a ~1-2 fps e a que custo — **antes** de construir o heatmap completo.

> Tudo aqui corre **no Jetson**. Não mexe na app `padel-streamer` nem no `.venv` dela.

## 1) Instalar (uma vez)

O passo delicado é o **PyTorch**: no Jetson tem de ser a wheel oficial da NVIDIA
para o teu JetPack (não o `pip install torch` normal).

```bash
cd ~/streamingpadel
git pull

# venv próprio para a análise (separado do .venv da app)
python3 -m venv ~/analytics-venv
source ~/analytics-venv/bin/activate
pip install --upgrade pip

# (a) PyTorch para Jetson:
#   Descobre a tua versão de JetPack:  sudo apt-cache show nvidia-jetpack | grep Version
#   Depois instala a wheel torch correspondente (guia oficial NVIDIA "PyTorch for Jetson").
#   Em JetPack 6.x muitas vezes basta:
#     pip install torch torchvision --index-url https://pypi.jetson-ai-lab.dev/jp6/cu126
#   (se este index falhar, segue o guia NVIDIA para a tua versão exacta)

# (b) resto das dependências:
pip install -r analytics/requirements-jetson.txt
```

Confirma que o torch vê a GPU:
```bash
python3 -c "import torch; print('CUDA:', torch.cuda.is_available())"
# tem de dizer  CUDA: True
```

## 2) Correr o teste

```bash
source ~/analytics-venv/bin/activate
cd ~/streamingpadel
python3 analytics/test_detect.py --ip 192.168.88.201 --user admin --password 'P@ssw0rd1535'
```

Opções úteis:
- `--seconds 30`  duração (default 30)
- `--fps 1`       frames analisados por segundo (default 1)
- `--conf 0.35`   confiança mínima
- `--model yolov8n.pt`  nano (mais leve). Se falhar a apanhar jogadores ao fundo,
  tenta `yolov8s.pt` (mais pesado, mais preciso).

## 3) Ler o resultado

No fim aparece um **RESUMO**. O que interessa:
- **frames com >=4** alto (idealmente perto de 100%) → apanha os 4 jogadores.
- **ms/frame** baixo → há folga para tempo real.
- Abre **`analytics/out/detect_sample.jpg`** e confirma com os olhos: as caixas
  verdes estão mesmo nos jogadores (e não a apanhar gente fora do court)?

### O que fazer com o resultado
- ✅ **Apanha bem os 4 + rápido** → avançamos para a Fase 1: calibração dos 4
  cantos do court + homografia + heatmap + página nova na plataforma.
- ⚠️ **Falha jogadores ao fundo** → subir para `--model yolov8s.pt` e repetir.
- ⚠️ **Apanha pessoas fora do court** (bancada, etc.) → resolve-se na Fase 1 com
  a máscara do court (só conta quem está dentro das linhas).
- ❌ **CUDA: False / muito lento** → o torch não está a usar a GPU; revê o passo 1.

Cola-me o RESUMO + diz se a imagem está boa, e eu preparo a Fase 1.
