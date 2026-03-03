#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Проверяем, что .env существует
if [[ ! -f ".env" ]]; then
  echo "ERROR: .env not found. Создайте его (скопируйте из .env.example) и заполните токены/пути."
  exit 1
fi

# Загружаем переменные окружения из .env
set -a
source .env
set +a

# Проверка обязательных переменных окружения
: "${TELEGRAM_BOT_TOKEN:?Отсутствует TELEGRAM_BOT_TOKEN в .env}"
: "${GIGACHAT_API_KEY:?Отсутствуют GIGACHAT_API_KEY в .env}"
: "${GOOGLE_SA_JSON:?Отсутствуют GOOGLE_SA_JSON в .env}"


# Создаём виртуальное окружение, если его нет
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi

# Активируем виртуальное окружение
source .venv/bin/activate

# Обновляем pip и устанавливаем зависимости
python -m pip install --upgrade pip
pip install -r requirements.txt

# Проверяем Redis и запускаем, если он не работает
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export REDIS_URL

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

# Если Redis работает через localhost, запускаем его в контейнере Docker, если не запущен
if [[ "$REDIS_HOST" == "localhost" || "$REDIS_HOST" == "127.0.0.1" ]]; then
  if command -v redis-cli >/dev/null 2>&1; then
    if ! redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "Redis не отвечает на $REDIS_HOST:$REDIS_PORT. Попытка запустить Redis через Docker..."
      if command -v docker >/dev/null 2>&1; then
        docker rm -f uni_agent_redis >/dev/null 2>&1 || true
        docker run --name uni_agent_redis -d -p "${REDIS_PORT}:6379" redis:7 >/dev/null
        echo "Redis был запущен в контейнере uni_agent_redis."
      else
        echo "Предупреждение: Docker не найден и Redis не работает. Установите/запустите Redis или укажите правильный REDIS_URL."
      fi
    fi
  else
    echo "Примечание: redis-cli не найден. Проверка Redis пропущена."
  fi
fi

# Запуск бота
exec python -m app.main