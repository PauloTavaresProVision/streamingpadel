"""Configuração da app via variáveis de ambiente / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Base de dados (SQLite, ficheiro único)
    database_url: str = "sqlite:///./padel_streamer.db"

    # Pasta para ficheiros estáticos gerados (logos, snapshots, perfis de ruído)
    data_dir: str = "./data"

    # ─── RTSP / câmara ───
    # Caminho default do stream Hikvision (canal principal). Pode ser sobreposto por court.
    default_rtsp_path: str = "/Streaming/Channels/101"

    # ─── YouTube RTMP ───
    rtmp_base_url: str = "rtmp://a.rtmp.youtube.com/live2"

    # ─── YouTube Data API (OAuth) ───
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    youtube_redirect_uri: str = "http://localhost:8000/api/youtube/callback"
    youtube_default_privacy: str = "unlisted"

    # ─── GStreamer ───
    # Caminho do binário (no Jetson é só "gst-launch-1.0").
    gst_launch_bin: str = "gst-launch-1.0"
    # Modelo RNNoise para denoise de áudio (opcional). Vazio = sem RNNoise.
    rnnoise_model_path: str = ""

    # Watchdog: se não houver progresso há N segundos, considera-se congelado.
    frozen_threshold_seconds: int = 30


settings = Settings()
