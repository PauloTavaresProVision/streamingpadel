"""Inicialização da base de dados SQLite + sessões."""
from sqlalchemy import inspect as sa_inspect, text
from sqlmodel import SQLModel, Session, create_engine, select

from .config import settings
from .models import Court, YouTubeOAuth

# check_same_thread=False — FastAPI usa threads diferentes por request.
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def _auto_migrate() -> None:
    """
    Adiciona colunas em falta às tabelas existentes (SQLite ALTER TABLE ADD COLUMN).
    Permite acrescentar campos ao modelo sem apagar a BD nem perder dados.
    """
    insp = sa_inspect(engine)
    for model in (Court, YouTubeOAuth):
        tname = model.__tablename__
        if tname not in insp.get_table_names():
            continue
        existing = {c["name"] for c in insp.get_columns(tname)}
        with engine.begin() as conn:
            for col in model.__table__.columns:
                if col.name in existing:
                    continue
                ctype = col.type.compile(dialect=engine.dialect)
                field = model.model_fields.get(col.name)
                default = getattr(field, "default", None) if field else None
                if isinstance(default, bool):
                    dsql = "1" if default else "0"
                elif isinstance(default, (int, float)):
                    dsql = str(default)
                elif isinstance(default, str):
                    dsql = "'" + default.replace("'", "''") + "'"
                else:
                    dsql = "NULL"
                conn.execute(text(f'ALTER TABLE "{tname}" ADD COLUMN "{col.name}" {ctype} DEFAULT {dsql}'))


def init_db() -> None:
    """Cria o schema (se não existir) + auto-migra colunas novas + seed inicial."""
    SQLModel.metadata.create_all(engine)
    _auto_migrate()
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
