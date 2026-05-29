"""Inicialização da base de dados SQLite + sessões."""
from sqlmodel import SQLModel, Session, create_engine, select

from .config import settings
from .models import Court, YouTubeOAuth

# check_same_thread=False — FastAPI usa threads diferentes por request.
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Cria o schema (se não existir) + um court de exemplo na primeira execução."""
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        # Seed: campo pré-configurado com a câmara conhecida se a BD estiver vazia.
        existing = session.exec(select(Court)).first()
        if existing is None:
            # Password vem do .env (settings.seed_nvr_password) — não hardcoded.
            session.add(Court(
                name="Campo 1",
                camera_ip=settings.seed_camera_ip,
                nvr_user=settings.seed_nvr_user,
                nvr_password=settings.seed_nvr_password,
                rtsp_path=settings.seed_rtsp_path,
                resolution="1080p",
                bitrate_kbps=4500,
                fps=25,
            ))
            session.commit()


def get_session():
    """Dependency do FastAPI: uma sessão por request."""
    with Session(engine) as session:
        yield session
