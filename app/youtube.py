"""Integração YouTube Data API v3 (OAuth + criar broadcasts) em Python."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlmodel import Session

from .config import settings
from .models import YouTubeOAuth, Court

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def is_server_configured() -> bool:
    return bool(settings.youtube_client_id and settings.youtube_client_secret and settings.youtube_redirect_uri)


def _client_config() -> dict:
    return {
        "web": {
            "client_id": settings.youtube_client_id,
            "client_secret": settings.youtube_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.youtube_redirect_uri],
        }
    }


def _get_row(session: Session) -> YouTubeOAuth:
    row = session.get(YouTubeOAuth, 1)
    if row is None:
        row = YouTubeOAuth(id=1)
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def oauth_status(session: Session) -> dict:
    row = session.get(YouTubeOAuth, 1)
    return {
        "is_server_configured": is_server_configured(),
        "is_connected": bool(row and row.refresh_token),
        "channel_id": row.channel_id if row else None,
        "channel_title": row.channel_title if row else None,
        "connected_at": row.connected_at.isoformat() if (row and row.connected_at) else None,
    }


def build_auth_url(state: str = "") -> str:
    if not is_server_configured():
        raise RuntimeError("Credenciais Google não configuradas (YOUTUBE_CLIENT_ID/SECRET).")
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=settings.youtube_redirect_uri)
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true", state=state or "padel"
    )
    return auth_url


def handle_callback(session: Session, code: str) -> dict:
    if not is_server_configured():
        raise RuntimeError("Servidor sem credenciais Google.")
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=settings.youtube_redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials
    if not creds.refresh_token:
        raise RuntimeError("Google não devolveu refresh_token. Revoga o acesso em myaccount.google.com/permissions e tenta de novo.")

    row = _get_row(session)
    is_new = row.connected_at is None
    row.refresh_token = creds.refresh_token
    row.access_token = creds.token
    row.access_token_expires_at = creds.expiry
    row.granted_scopes = " ".join(creds.scopes or [])
    if is_new:
        row.connected_at = datetime.utcnow()
    row.last_used_at = datetime.utcnow()
    session.add(row)
    session.commit()

    # info do canal
    try:
        yt = _service(session, row)
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            row.channel_id = items[0]["id"]
            row.channel_title = items[0]["snippet"]["title"]
            session.add(row)
            session.commit()
    except Exception:
        pass

    return oauth_status(session)


def disconnect(session: Session) -> None:
    row = session.get(YouTubeOAuth, 1)
    if row:
        session.delete(row)
        session.commit()


def _service(session: Session, row: YouTubeOAuth):
    creds = Credentials(
        token=row.access_token,
        refresh_token=row.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.youtube_client_id,
        client_secret=settings.youtube_client_secret,
        scopes=SCOPES,
    )
    if not creds.valid:
        creds.refresh(Request())
        row.access_token = creds.token
        row.access_token_expires_at = creds.expiry
        row.last_used_at = datetime.utcnow()
        session.add(row)
        session.commit()
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def create_broadcast(session: Session, court: Court, title: str,
                     description: str = "", privacy: str = "unlisted") -> dict:
    row = session.get(YouTubeOAuth, 1)
    if not row or not row.refresh_token:
        raise RuntimeError("Conta YouTube não ligada.")

    yt = _service(session, row)
    start = datetime.now(timezone.utc) + timedelta(minutes=1)
    priv = privacy if privacy in ("public", "unlisted", "private") else "unlisted"

    broadcast = yt.liveBroadcasts().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {"title": title, "description": description or "",
                        "scheduledStartTime": start.isoformat().replace("+00:00", "Z")},
            "status": {"privacyStatus": priv, "selfDeclaredMadeForKids": False},
            "contentDetails": {"enableAutoStart": True, "enableAutoStop": True,
                               "enableDvr": True, "recordFromStart": True,
                               "monitorStream": {"enableMonitorStream": False}},
        },
    ).execute()

    stream = yt.liveStreams().insert(
        part="snippet,cdn,contentDetails",
        body={
            "snippet": {"title": f"Stream — {title}"},
            "cdn": {"format": "1080p", "ingestionType": "rtmp",
                    "resolution": "1080p", "frameRate": "30fps"},
        },
    ).execute()

    yt.liveBroadcasts().bind(id=broadcast["id"], part="id,contentDetails", streamId=stream["id"]).execute()

    stream_key = stream.get("cdn", {}).get("ingestionInfo", {}).get("streamName", "")
    watch_url = f"https://www.youtube.com/watch?v={broadcast['id']}"

    court.youtube_stream_key = stream_key
    court.youtube_broadcast_id = broadcast["id"]
    court.youtube_watch_url = watch_url
    session.add(court)
    session.commit()

    return {
        "broadcast_id": broadcast["id"],
        "stream_key": stream_key,
        "watch_url": watch_url,
        "studio_url": f"https://studio.youtube.com/video/{broadcast['id']}/livestreaming",
    }
