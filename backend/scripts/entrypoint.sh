#!/bin/sh
set -eu

if [ "${SKIP_DB_MIGRATE:-0}" != "1" ]; then
  echo "Running database migrations (alembic upgrade head)..."
  i=0
  until alembic upgrade head; do
    i=$((i + 1))
    if [ "$i" -ge 8 ]; then
      echo "Migrations failed after retries." >&2
      exit 1
    fi
    echo "Migration attempt $i failed (possible concurrent migrator); retrying..."
    sleep 2
  done
  echo "Migrations complete."
fi

exec "$@"
