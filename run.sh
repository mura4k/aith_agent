#!/usr/bin/env bash
set -euo pipefail

# Go to repo root (directory of this script)
cd "$(dirname "$0")"

if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Create it (copy from .env.example) and fill tokens/paths."
  exit 1
fi

# Load env vars from .env safely (no export of comments)
set -a
# shellcheck disable=SC1091
source .env
set +a

# Basic checks
: "${TELEGRAM_BOT_TOKEN:?Missing TELEGRAM_BOT_TOKEN in .env}"
: "${OPENROUTER_API_KEY:?Missing OPENROUTER_API_KEY in .env}"
: "${GOOGLE_SA_JSON:?Missing GOOGLE_SA_JSON in .env}"

if [[ ! -f "$GOOGLE_SA_JSON" ]]; then
  echo "ERROR: GOOGLE_SA_JSON file not found at: $GOOGLE_SA_JSON"
  exit 1
fi

# Create venv if needed
if [[ ! -d ".venv" ]]; then
  python -m venv .venv
fi

# Activate venv
# shellcheck disable=SC1091
source .venv/bin/activate

# Upgrade pip + install deps
python -m pip install --upgrade pip
pip install -r requirements.txt

# Start redis if REDIS_URL points to localhost and redis isn't running
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export REDIS_URL

# A small best-effort redis check
REDIS_HOST="$(python - <<'PY'
import os, re
u=os.environ.get("REDIS_URL","redis://localhost:6379/0")
m=re.match(r"redis://([^:/]+)(?::(\d+))?/", u)
print(m.group(1) if m else "localhost")
PY
)"
REDIS_PORT="$(python - <<'PY'
import os, re
u=os.environ.get("REDIS_URL","redis://localhost:6379/0")
m=re.match(r"redis://([^:/]+)(?::(\d+))?/", u)
print(m.group(2) if m and m.group(2) else "6379")
PY
)"

# Only try to run local docker redis if host looks like localhost
if [[ "$REDIS_HOST" == "localhost" || "$REDIS_HOST" == "127.0.0.1" ]]; then
  if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Redis not responding on $REDIS_HOST:$REDIS_PORT. Trying to start via Docker..."
      if command -v docker >/dev/null 2>&1; then
        docker rm -f uni_agent_redis >/dev/null 2>&1 || true
        docker run --name uni_agent_redis -d -p "${REDIS_PORT}:6379" redis:7 >/dev/null
        echo "Started Redis container uni_agent_redis."
      else
        echo "WARNING: docker not found and redis not running. Install/start Redis or set REDIS_URL to a running Redis."
      fi
    fi
  else
    echo "Note: redis-cli not found. Skipping Redis health check."
  fi
fi

# Run the bot
exec python -m app.main