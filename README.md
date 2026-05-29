# padel-streamer

App dedicada de **transmissão YouTube** para correr no **NVIDIA Jetson Orin NX**
(Ubuntu/JetPack), usando o encoder de hardware **NVENC** via **GStreamer**.

Separada do GameVision — faz só uma coisa: pegar no RTSP de uma câmara, compor
(scale, logo, texto/hora), e empurrar para o YouTube Live com latência baixa e
sem cortes (o NVENC do Jetson tem folga enorme para 1-3 câmaras a 1080p).

## Arquitectura

```
Câmara RTSP ──► GStreamer (nvv4l2decoder ─► nvvidconv ─► nvv4l2h264enc) ──► RTMP ──► YouTube
                         ▲
                  FastAPI + SQLite
                  (config, start/stop, OAuth, criar broadcast)
```

- **FastAPI** — API REST + UI
- **SQLite** — config dos campos/câmaras (1 ficheiro)
- **GStreamer** — `gst-launch-1.0` por shell-out (pipeline validado no Orin NX)
- **YouTube Data API** — OAuth + criar transmissões automaticamente

## Requisitos (Jetson)

JetPack 5.x já traz o GStreamer + plugins NVIDIA. Confirma:

```bash
gst-inspect-1.0 nvv4l2h264enc   # encoder NVENC
gst-inspect-1.0 nvvidconv       # scale/convert GPU
gst-inspect-1.0 nvv4l2decoder   # decode HW
```

Python 3.10+.

## Instalação

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edita conforme necessário
```

## Correr

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

API em `http://<ip-do-jetson>:8000`. Docs interactivos em `/docs`.

## Endpoints principais

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/courts` | Lista campos |
| POST | `/api/courts` | Cria campo |
| PUT | `/api/courts/{id}` | Actualiza config |
| POST | `/api/courts/{id}/start` | Inicia transmissão |
| POST | `/api/courts/{id}/stop` | Pára transmissão |
| GET | `/api/courts/{id}/status` | Estado |
| GET | `/api/courts/{id}/snapshot` | Frame JPEG da câmara |
| GET | `/api/health` | Saúde |

## Estado actual

- [x] Scaffold FastAPI + SQLite
- [x] Modelos (Court + config completa)
- [x] GStreamer manager (pipeline NVENC + start/stop/status)
- [x] Endpoints REST (CRUD + streaming + snapshot)
- [ ] YouTube OAuth + criar broadcast (Python)
- [ ] UI mínima
- [ ] Áudio real da câmara + denoise RNNoise
- [ ] Logo overlay + crop
- [ ] systemd service (arranque automático)
