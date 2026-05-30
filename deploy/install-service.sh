#!/usr/bin/env bash
# Instala o padel-streamer como serviço systemd (arranca no boot, reinicia se cair).
# Correr no Jetson:  bash deploy/install-service.sh
set -e

SERVICE=padel-streamer
SRC="$(cd "$(dirname "$0")" && pwd)/${SERVICE}.service"

echo "==> A instalar ${SERVICE}.service em /etc/systemd/system/"
sudo cp "$SRC" "/etc/systemd/system/${SERVICE}.service"

echo "==> A recarregar o systemd"
sudo systemctl daemon-reload

echo "==> A activar no boot + arrancar agora"
sudo systemctl enable "${SERVICE}"
sudo systemctl restart "${SERVICE}"

echo "==> Estado:"
sudo systemctl --no-pager status "${SERVICE}" | head -12

cat <<'EOF'

Pronto. Comandos úteis:
  sudo systemctl status padel-streamer      # ver estado
  journalctl -u padel-streamer -f           # ver logs ao vivo
  sudo systemctl restart padel-streamer     # reiniciar
  sudo systemctl stop padel-streamer        # parar
  sudo systemctl disable padel-streamer     # desactivar no boot

NOTA: antes de instalar, pára o uvicorn manual que tens a correr:
  pkill -f "uvicorn app.main"
EOF
