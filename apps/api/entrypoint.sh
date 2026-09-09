#!/bin/bash
set -e

echo "Starting deployment process..."

# Navigate to api directory if needed
# cd apps/api

# Run database migrations
# Assuming alembic is configured at the root or within apps/api
# We will use the python module path if run from root
if [ -f "alembic.ini" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

echo "Starting server..."
# Run the application
exec "$@"
