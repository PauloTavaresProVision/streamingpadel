"""Teste de velocidade da internet (Ookla speedtest-cli). Resultado cacheado."""
from __future__ import annotations

import threading
import time
from typing import Optional

_lock = threading.Lock()
_last: Optional[dict] = None
_running = False


def get_last() -> Optional[dict]:
    return _last


def is_running() -> bool:
    return _running


def run_test() -> dict:
    """Corre um teste de velocidade (bloqueante ~15-30s). Devolve down/up/ping em Mbps/ms."""
    global _last, _running
    with _lock:
        if _running:
            return {"running": True, **(_last or {})}
        _running = True
    try:
        import speedtest  # import tardio (só quando há teste)
        st = speedtest.Speedtest(secure=True)
        st.get_best_server()
        down = st.download() / 1_000_000      # bps -> Mbps
        up = st.upload() / 1_000_000
        ping = st.results.ping
        _last = {
            "download_mbps": round(down, 1),
            "upload_mbps": round(up, 1),
            "ping_ms": round(ping, 1),
            "ran_at": time.time(),
            "ok": True,
        }
        return _last
    except Exception as e:
        _last = {"ok": False, "error": str(e), "ran_at": time.time()}
        return _last
    finally:
        _running = False
