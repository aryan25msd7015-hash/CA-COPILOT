#!/bin/sh
set -eu

echo "Running database migrations (alembic upgrade head)..."
alembic upgrade head
echo "Migrations complete."

exec "$@"
