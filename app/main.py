"""padel-streamer — API FastAPI para transmissão YouTube no Jetson (GStreamer NVENC)."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

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


@app.put("/api/courts/{court_id}")
def update_court(court_id: str, data: CourtUpsert, session: Session = Depends(get_session)):
    court = session.get(Court, court_id)
    if not court:
        raise HTTPException(404, "Court não encontrado")
    updates = data.model_dump(exclude_unset=True)
    # clamps de segurança
    if "logo_size_percent" in updates and updates["logo_size_percent"] is not None:
        updates["logo_size_percent"] = max(5, min(updates["logo_size_percent"], 30))
    if "logo_opacity" in updates and updates["logo_opacity"] is not None:
        updates["logo_opacity"] = max(10, min(updates["logo_opacity"], 100))
    if "overlay_font_size" in updates and updates["overlay_font_size"] is not None:
        updates["overlay_font_size"] = max(12, min(updates["overlay_font_size"], 72))
    if "audio_volume" in updates and updates["audio_volume"] is not None:
        updates["audio_volume"] = max(0.1, min(updates["audio_volume"], 5.0))
    if "audio_denoise_strength" in updates and updates["audio_denoise_strength"] is not None:
        updates["audio_denoise_strength"] = max(5, min(updates["audio_denoise_strength"], 30))
    for k, v in updates.items():
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


@app.get("/api/health")
def health():
    return {"status": "ok", "gst_bin": settings.gst_launch_bin}


# ─────────────────────────── UI ───────────────────────────
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"))
