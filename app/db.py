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
        # Seed: 1 court de exemplo se a BD estiver vazia
        existing = session.exec(select(Court)).first()
        if existing is None:
            session.add(Court(name="Campo 1"))
            session.commit()


def get_session():
    """Dependency do FastAPI: uma sessão por request."""
    with Session(engine) as session:
        yield session
