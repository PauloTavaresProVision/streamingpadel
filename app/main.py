"""padel-streamer — API FastAPI para transmissão YouTube no Jetson (GStreamer NVENC)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Response, UploadFile, File, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlmodel import Session, select

from . import auth, youtube
from .config import settings
from .db import init_db, get_session, engine
from .models import Court
from .gstreamer import manager, capture_snapshot


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield
    manager.stop_all()


app = FastAPI(title="padel-streamer", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────── Auth middleware ───────────────────────────
# Protege /api/* excepto: login, health, callback OAuth e imagens (snapshot)
# que são carregadas por <img> sem header Authorization.
_AUTH_EXEMPT = {"/api/login", "/api/health", "/api/youtube/callback"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    needs_auth = (
        path.startswith("/api/")
        and path not in _AUTH_EXEMPT
        and not path.endswith("/snapshot")  # imagens via <img>
    )
    if needs_auth:
        hdr = request.headers.get("authorization", "")
        token = hdr[7:].strip() if hdr.lower().startswith("bearer ") else ""
        if not auth.verify_token(token):
            return JSONResponse({"detail": "Não autenticado"}, status_code=401)
    return await call_next(request)


# ─────────────────────────── Login ───────────────────────────
class LoginIn(BaseModel):
    password: str


@app.post("/api/login")
def login(data: LoginIn):
    token = auth.make_token(data.password)
    if not token:
        raise HTTPException(401, "Password incorrecta")
    return {"token": token}


# ─────────────────────────── Schemas ───────────────────────────
class CourtUpsert(BaseModel):
    """Campos editáveis de um court (todos opcionais para updates parciais)."""
    name: Optional[str] = None
    camera_ip: Optional[str] = None
    nvr_user: Optional[str] = None
    nvr_password: Optional[str] = None
    rtsp_path: Optional[str] = None
    youtube_stream_key: Optional[str] = None
    logo_position: Optional[str] = None
    logo_size_percent: Optional[int] = None
    logo_opacity: Optional[int] = None
    resolution: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    fps: Optional[int] = None
    crop_region: Optional[str] = None
    overlay_text: Optional[str] = None
    show_clock: Optional[bool] = None
    overlay_text_position: Optional[str] = None
    overlay_font_size: Optional[int] = None
    overlay_font_color: Optional[str] = None
    overlay_font_family: Optional[str] = None
    audio_volume: Optional[float] = None
    audio_normalize: Optional[bool] = None
    audio_denoise: Optional[bool] = None
    audio_denoise_strength: Optional[int] = None


# ─────────────────────────── Courts CRUD ───────────────────────────
@app.get("/api/courts")
def list_courts(session: Session = Depends(get_session)):
    return session.exec(select(Court)).all()


@app.get("/api/courts/{court_id}")
def get_court(court_id: str, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    return court


@app.post("/api/courts", status_code=201)
def create_court(data: CourtUpsert, session: Session = Depends(get_session)):
    court = Court(**{k: v for k, v in data.model_dump().items() if v is not None})
    session.add(court)
    session.commit()
    session.refresh(court)
    return court


_CLAMPS = {
    "logo_size_percent": (5, 30),
    "logo_opacity": (10, 100),
    "overlay_font_size": (12, 120),
    "audio_volume": (0.1, 5.0),
    "audio_denoise_strength": (5, 30),
}


@app.put("/api/courts/{court_id}")
def update_court(court_id: str, data: dict = Body(...), session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    # Aplica apenas campos válidos do Court (auto-suporta campos novos), com clamps.
    valid = set(Court.model_fields.keys()) - {"id"}
    for k, v in data.items():
        if k not in valid:
            continue
        if k in _CLAMPS and v is not None:
            lo, hi = _CLAMPS[k]
            v = max(lo, min(v, hi))
        setattr(court, k, v)
    session.add(court)
    session.commit()
    session.refresh(court)
    return court


@app.delete("/api/courts/{court_id}", status_code=204)
def delete_court(court_id: str, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    manager.stop(court_id)
    session.delete(court)
    session.commit()


# ─────────────────────────── Streaming ───────────────────────────
@app.post("/api/courts/{court_id}/start")
def start_stream(court_id: str, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    if not court.youtube_stream_key:
        raise HTTPException(400, "Stream key não configurada para este court.")
    try:
        state = manager.start(court)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return manager.status(court_id)


@app.post("/api/courts/{court_id}/stop")
def stop_stream(court_id: str):
    ok = manager.stop(court_id)
    return {"stopped": ok, **manager.status(court_id)}


@app.get("/api/courts/{court_id}/status")
def stream_status(court_id: str):
    return manager.status(court_id)


@app.get("/api/status")
def all_status(session: Session = Depends(get_session)):
    courts = session.exec(select(Court)).all()
    return [manager.status(c.id) for c in courts]


# ─────────────────────────── Snapshot ───────────────────────────
@app.get("/api/courts/{court_id}/snapshot")
def snapshot(court_id: str, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    img = capture_snapshot(court)
    if not img:
        raise HTTPException(503, "Não foi possível capturar snapshot da câmara.")
    return Response(content=img, media_type="image/jpeg")


_ALLOWED_LOGO = {".png", ".jpg", ".jpeg", ".webp"}


@app.post("/api/courts/{court_id}/logo")
async def upload_logo(court_id: str, file: UploadFile = File(...), session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_LOGO:
        raise HTTPException(400, f"Formato não suportado. Permitidos: {', '.join(_ALLOWED_LOGO)}")

    logo_dir = os.path.join(settings.data_dir, "logos")
    os.makedirs(logo_dir, exist_ok=True)
    fname = f"logo_{court_id}{ext}"
    abs_path = os.path.join(logo_dir, fname)
    with open(abs_path, "wb") as f:
        f.write(await file.read())

    rel = f"logos/{fname}"
    court.logo_path = rel
    session.add(court)
    session.commit()
    return {"logo_path": rel, "logo_url": f"/data/{rel}"}


# ─────────────────────────── YouTube OAuth + broadcast ───────────────────────────
@app.get("/api/youtube/status")
def yt_status(session: Session = Depends(get_session)):
    return youtube.oauth_status(session)


@app.get("/api/youtube/auth-url")
def yt_auth_url():
    try:
        return {"auth_url": youtube.build_auth_url()}
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/youtube/callback", include_in_schema=False)
def yt_callback(code: str = "", error: str = "", session: Session = Depends(get_session)):
    if error:
        return HTMLResponse(_oauth_html(False, f"Google: {error}"))
    if not code:
        return HTMLResponse(_oauth_html(False, "Sem authorization code"))
    try:
        st = youtube.handle_callback(session, code)
        return HTMLResponse(_oauth_html(True, f"Ligado: {st.get('channel_title') or 'canal'}"))
    except Exception as e:
        return HTMLResponse(_oauth_html(False, str(e)))


@app.post("/api/youtube/disconnect")
def yt_disconnect(session: Session = Depends(get_session)):
    youtube.disconnect(session)
    return {"ok": True}


class CreateBroadcastIn(BaseModel):
    title: str
    description: Optional[str] = None
    privacy: str = "unlisted"


@app.post("/api/courts/{court_id}/create-broadcast")
def create_broadcast(court_id: str, data: CreateBroadcastIn, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    if not data.title.strip():
        raise HTTPException(400, "Título obrigatório")
    try:
        return youtube.create_broadcast(session, court, data.title.strip(), data.description or "", data.privacy)
    except Exception as e:
        raise HTTPException(400, str(e))


def _oauth_html(ok: bool, msg: str) -> str:
    color = "#16a34a" if ok else "#dc2626"
    icon = "✓" if ok else "✗"
    title = "Conta YouTube ligada!" if ok else "Falha ao ligar"
    safe = (msg or "").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>YouTube OAuth</title>
<style>body{{font-family:-apple-system,Segoe UI,Arial;background:#f8fafc;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
.c{{background:#fff;padding:32px;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:420px;text-align:center}}
.i{{font-size:48px;color:{color}}}h1{{font-size:20px}}p{{color:#475569}}button{{background:#0f172a;color:#fff;border:0;padding:10px 20px;border-radius:8px;cursor:pointer}}</style></head>
<body><div class='c'><div class='i'>{icon}</div><h1>{title}</h1><p>{safe}</p>
<button onclick='window.close()'>Fechar</button></div>
<script>try{{if(window.opener)window.opener.postMessage({{type:'youtube-oauth-result',success:{str(ok).lower()}}},'*')}}catch(e){{}}
setTimeout(function(){{try{{window.close()}}catch(e){{}}}},2000)</script></body></html>"""


@app.get("/api/health")
def health():
    return {"status": "ok", "gst_bin": settings.gst_launch_bin}


# ─────────────────────────── Estáticos / UI ───────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_WEBDIST = os.path.join(os.path.dirname(__file__), "webdist")

# Serve ficheiros de dados (logos carregados) em /data
os.makedirs(settings.data_dir, exist_ok=True)
app.mount("/data", StaticFiles(directory=settings.data_dir), name="data")

# Serve os assets do build React em /assets (se o build existir)
_assets = os.path.join(_WEBDIST, "assets")
if os.path.isdir(_assets):
    app.mount("/assets", StaticFiles(directory=_assets), name="assets")


@app.get("/", include_in_schema=False)
def index():
    # UI rica (React) se houver build; senão a página simples.
    react_index = os.path.join(_WEBDIST, "index.html")
    if os.path.exists(react_index):
        return FileResponse(react_index)
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))


@app.get("/test", include_in_schema=False)
def test_page():
    # Página simples vanilla — só para testar câmaras.
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
