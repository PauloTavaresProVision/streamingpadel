"""Autenticação simples por password de admin (token stateless sha256)."""
import hashlib
import hmac

from fastapi import Header, HTTPException

from .config import settings


def _expected_token() -> str:
    """Token determinístico derivado da password + segredo. Sobrevive a restarts."""
    raw = f"{settings.admin_password}:{settings.auth_secret}".encode()
    return hashlib.sha256(raw).hexdigest()


def make_token(password: str) -> str | None:
    """Valida a password; devolve o token se correcta, senão None."""
    if hmac.compare_digest(password or "", settings.admin_password):
        return _expected_token()
    return None


def verify_token(token: str) -> bool:
    return hmac.compare_digest(token or "", _expected_token())


def require_auth(authorization: str = Header(default="")) -> None:
    """Dependency FastAPI: exige 'Authorization: Bearer <token>' válido."""
    token = ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Não autenticado")
