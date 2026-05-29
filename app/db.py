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
            # 7 campos reais do clube. IPs internos (não sensíveis); todos admin;
            # password única vem do .env (settings.seed_nvr_password) — não hardcoded.
            seed_courts = [
                ("ATC", "192.168.88.206"),
                ("CANDANDO", "192.168.88.205"),
                ("DELTA Q", "192.168.88.207"),
                ("HP STYLUS", "192.168.88.203"),
                ("STANDARD BANK", "192.168.88.201"),
                ("UCALL", "192.168.88.204"),
                ("VHG", "192.168.88.202"),
            ]
            for cname, cip in seed_courts:
                session.add(Court(
                    name=cname,
                    camera_ip=cip,
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
