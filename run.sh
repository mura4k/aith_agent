set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Copy .env.example -> .env and fill it."
  exit 1
fi

set -a
source .env
set +a

: "${TELEGRAM_BOT_TOKEN:?Missing TELEGRAM_BOT_TOKEN}"
: "${OPENROUTER_API_KEY:?Missing OPENROUTER_API_KEY}"
: "${GOOGLE_SA_JSON:?Missing GOOGLE_SA_JSON}"

if [[ ! -f "$GOOGLE_SA_JSON" ]]; then
  echo "ERROR: GOOGLE_SA_JSON not found at $GOOGLE_SA_JSON"
  exit 1
fi

REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export REDIS_URL

if command -v redis-cli >/dev/null 2>&1; then
  if ! redis-cli ping >/dev/null 2>&1; then
    echo "WARNING: Redis is not running. Start it with:"
    echo "  sudo systemctl enable --now redis-server"
    echo "or:"
    echo "  redis-server --daemonize yes"
  fi
else
  echo "NOTE: redis-cli not found (install redis-tools/redis-server) if you want checks."
fi

if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

exec python -m app.main