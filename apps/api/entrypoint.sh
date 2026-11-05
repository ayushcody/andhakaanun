#!/bin/bash
set -e

# Alembic is configured to run from apps/api/db (script_location = migrations).
# The API works without PostgreSQL, so a failed migration is logged, not fatal.
echo "Running database migrations..."
if (cd /app/apps/api/db && alembic upgrade head); then
    echo "Migrations applied."
else
    echo "Migrations skipped: database not reachable. The API will keep cases in memory."
fi

echo "Starting server..."
exec "$@"
