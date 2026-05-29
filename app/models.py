"""Modelos SQLite (SQLModel). Um Court = uma câmara + a sua configuração de stream."""
from datetime import datetime
from typing import Optional
import uuid

from sqlmodel import SQLModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


class Court(SQLModel, table=True):
    """Campo de padel: câmara + configuração completa de transmissão YouTube."""

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = "Campo 1"

    # ─── Câmara / RTSP ───
    camera_ip: str = ""
    nvr_user: str = "admin"
    nvr_password: str = ""
    # Caminho RTSP (None = usa o default das settings)
    rtsp_path: Optional[str] = None

    # ─── YouTube ───
    youtube_stream_key: Optional[str] = None
    youtube_broadcast_id: Optional[str] = None
    youtube_watch_url: Optional[str] = None

    # ─── Logo ───
    logo_path: Optional[str] = None                 # relativo a data_dir
    logo_position: str = "TopRight"                 # TopLeft|TopRight|BottomLeft|BottomRight|None|"x,y"
    logo_size_percent: int = 10                     # 5-30
    logo_opacity: int = 100                         # 10-100

    # ─── Vídeo ───
    resolution: str = "1080p"                       # 720p | 1080p
    bitrate_kbps: int = 4500
    fps: int = 25
    # "X,Y,W,H" em % (0-100) ou None = sem crop
    crop_region: Optional[str] = None

    # ─── Overlay texto / hora ───
    overlay_text: Optional[str] = None
    show_clock: bool = False
    overlay_text_position: str = "BottomLeft"       # TopLeft|TopCenter|TopRight|BottomLeft|BottomCenter|BottomRight
    overlay_font_size: int = 24                     # 12-72
    overlay_font_color: str = "white"               # "#RRGGBB" ou nome
    overlay_font_family: str = "Sans"               # Sans|Serif|Monospace (Pango font family)

    # ─── Áudio ───
    audio_volume: float = 1.0                       # 0.1-5.0
    audio_normalize: bool = False
    audio_denoise: bool = False
    audio_denoise_strength: int = 15                # 5-30 (dB)
    noise_profile_path: Optional[str] = None
    noise_floor_db: Optional[float] = None
    noise_profile_captured_at: Optional[datetime] = None


class YouTubeOAuth(SQLModel, table=True):
    """Credenciais OAuth do Google (singleton — uma conta partilhada por todos os courts)."""

    # PK fixa para garantir uma única linha.
    id: int = Field(default=1, primary_key=True)
    refresh_token: Optional[str] = None
    access_token: Optional[str] = None
    access_token_expires_at: Optional[datetime] = None
    granted_scopes: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
