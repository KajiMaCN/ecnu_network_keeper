#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVICE_NAME="ecnu-network-keeper"
SERVICE_USER="${SUDO_USER:-${USER}}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
ENV_FILE="${ENV_FILE:-${PROJECT_DIR}/deploy/systemd/.env}"
INTERVAL="${ECNU_KEEPER_INTERVAL:-120}"
VERBOSE_FLAG="--verbose"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      SERVICE_USER="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --service-name)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    --no-verbose)
      VERBOSE_FLAG=""
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Please run this script with sudo." >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found or not executable: $PYTHON_BIN" >&2
  exit 1
fi

HOME_DIR="$(getent passwd "$SERVICE_USER" | cut -d: -f6)"
if [[ -z "$HOME_DIR" ]]; then
  echo "Unable to resolve home directory for user: $SERVICE_USER" >&2
  exit 1
fi

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
EXEC_START=("$PYTHON_BIN" -m ecnu_network_keeper --login --daemon)
if [[ -n "$VERBOSE_FLAG" ]]; then
  EXEC_START+=("$VERBOSE_FLAG")
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ECNU Network Keeper
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${PROJECT_DIR}
Environment=PYTHONUNBUFFERED=1
Environment=HOME=${HOME_DIR}
Environment=ECNU_KEEPER_INTERVAL=${INTERVAL}
EnvironmentFile=-${ENV_FILE}
ExecStart=${EXEC_START[*]}
Restart=always
RestartSec=10
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "Installed ${SERVICE_NAME} -> ${SERVICE_FILE}"
echo "Environment file: ${ENV_FILE}"
echo "Start it with: sudo systemctl start ${SERVICE_NAME}"
echo "Logs with: sudo journalctl -u ${SERVICE_NAME} -f"
