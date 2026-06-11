# Análise de jogo — Heatmap de jogadores (Fase 0: teste de viabilidade)

Esta pasta é **independente** da app de streaming. O objetivo da Fase 0 é
confirmar, no Jetson, se conseguimos detetar os 4 jogadores de uma câmara fixa
a ~1-2 fps e a que custo — **antes** de construir o heatmap completo.

> Tudo aqui corre **no Jetson**. Não mexe na app `padel-streamer` nem no `.venv` dela.

## 1) Instalar (uma vez) — JetPack 5.1.1 (L4T R35.3.1, CUDA 11.4, Python 3.8)

> ⚠️ **Crítico:** as wheels de PyTorch da NVIDIA para JetPack 5.1.x são para
> **Python 3.8** (`cp38`). O venv TEM de ser criado com o `python3.8` do sistema —
> **não** uses o conda `base` (Python mais recente), senão a wheel não instala.
> Primeiro desativa o conda nesta sessão:

```bash
conda deactivate 2>/dev/null   # sai do (base); repete se necessário
cd ~/streamingpadel
git pull

# venv com o Python 3.8 do SISTEMA (não o do conda).
# --system-site-packages → o venv VÊ o opencv com CUDA que já vem no JetPack.
/usr/bin/python3.8 -m venv --system-site-packages ~/analytics-venv
source ~/analytics-venv/bin/activate
python --version          # tem de dizer Python 3.8.x
python -c "import cv2; print('opencv do sistema:', cv2.__version__)"   # deve imprimir uma versão
pip install --upgrade pip setuptools wheel
```

**(a) PyTorch para JetPack 5.1.1** — wheel oficial NVIDIA (torch 2.1.0 / cp38).
Dependências de sistema + a wheel:
```bash
sudo apt-get install -y libopenblas-base libopenmpi-dev libomp-dev

# torch 2.1.0 para JetPack 5.1 (cp38). Link oficial NVIDIA (Jetson forums / developer.download):
wget https://developer.download.nvidia.com/compute/redist/jp/v51/pytorch/torch-2.1.0a0+41361538.nv23.06-cp38-cp38-linux_aarch64.whl -O torch-2.1.0-cp38.whl
pip install numpy=='1.24.4'      # compatível com torch 2.1 em cp38
pip install torch-2.1.0-cp38.whl
```

> Se o link der 404, o ficheiro está no índice oficial NVIDIA "PyTorch for Jetson"
> (procura a secção **JetPack 5.1 / torch 2.1.0**). Cola-me o erro e eu confirmo o URL exato.

**(b) torchvision 0.16.0** (tem de condizer com torch 2.1 — compilar do source):
```bash
sudo apt-get install -y libjpeg-dev zlib1g-dev
pip install 'pillow<10'
git clone --branch v0.16.0 https://github.com/pytorch/vision torchvision_src
cd torchvision_src && export BUILD_VERSION=0.16.0 && python setup.py install && cd ..
```

**(c) resto das dependências** (ultralytics + opencv):
```bash
pip install -r analytics/requirements-jetson.txt
```

Confirma que o torch vê a GPU:
```bash
python -c "import torch; print('torch', torch.__version__, '| CUDA:', torch.cuda.is_available())"
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
