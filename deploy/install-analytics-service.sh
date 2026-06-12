#!/usr/bin/env bash
# Instala o padel-analytics (heatmap, porta 8001) como serviço systemd:
# arranca no boot e reinicia se cair. Correr no Jetson:
#   bash deploy/install-analytics-service.sh
set -e

SERVICE=padel-analytics
SRC="$(cd "$(dirname "$0")" && pwd)/${SERVICE}.service"
ENVF="$HOME/streamingpadel/.analytics.env"

# 1) ficheiro de credenciais da câmara (só se ainda não existir)
if [ ! -f "$ENVF" ]; then
  echo "==> A criar ${ENVF} (edita se a câmara mudar)"
  cat > "$ENVF" <<'EOF'
CAM_IP=192.168.88.201
CAM_USER=admin
CAM_PASSWORD=P@ssw0rd1535
# CAM_PATH=/Streaming/Channels/101
# ANALYTICS_PORT=8001
EOF
  chmod 600 "$ENVF"
fi

echo "==> A instalar ${SERVICE}.service em /etc/systemd/system/"
sudo cp "$SRC" "/etc/systemd/system/${SERVICE}.service"

echo "==> A recarregar o systemd"
sudo systemctl daemon-reload

echo "==> A activar no boot + arrancar agora"
sudo systemctl enable "${SERVICE}"
sudo systemctl restart "${SERVICE}"

echo "==> Estado:"
sudo systemctl --no-pager status "${SERVICE}" | head -10

cat <<'EOF'

Pronto. A app de análise fica em http://<ip-do-jetson>:8001/
Comandos úteis:
  sudo systemctl status padel-analytics
  journalctl -u padel-analytics -f
  sudo systemctl restart padel-analytics

NOTA: pára primeiro a instância manual, se estiver a correr:
  pkill -f heatmap_app
EOF
