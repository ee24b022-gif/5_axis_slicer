#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "[entrypoint] Waiting for PostgreSQL..."
until python -c "
import socket, sys, os
url = os.environ.get('DATABASE_URL', '')
if 'postgresql' not in url:
    sys.exit(0)
# Extract host:port from postgresql+psycopg://user:pass@host:port/db
parts = url.split('@')
if len(parts) < 2:
    sys.exit(0)
host_port = parts[1].split('/')[0]
host, port = host_port.split(':') if ':' in host_port else (host_port, '5432')
s = socket.create_connection((host, int(port)), timeout=2)
s.close()
" 2>/dev/null; do
  echo "[entrypoint] PostgreSQL not ready, retrying in 1s..."
  sleep 1
done
echo "[entrypoint] PostgreSQL is ready."

# Run database migrations
echo "[entrypoint] Running Alembic migrations..."
alembic upgrade head
echo "[entrypoint] Migrations complete."

# Seed machine profiles
echo "[entrypoint] Seeding machine profiles..."
python -c "
from database import engine, Base, SessionLocal
from machine_profile_seed import seed_profiles
Base.metadata.create_all(bind=engine)
db = SessionLocal()
try:
    seed_profiles(db)
finally:
    db.close()
" 2>/dev/null || echo "[entrypoint] Profile seeding skipped (may already exist)."

# Dispatch based on the CMD argument
case "${1}" in
  api)
    echo "[entrypoint] Starting API server..."
    exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ;;
  worker)
    echo "[entrypoint] Starting Celery worker..."
    exec celery -A celery_app.celery_app worker --loglevel=info --concurrency=${WORKER_CONCURRENCY:-4}
    ;;
  beat)
    echo "[entrypoint] Starting Celery beat scheduler..."
    exec celery -A celery_app.celery_app beat --loglevel=info
    ;;
  *)
    echo "[entrypoint] Running custom command: $@"
    exec "$@"
    ;;
esac
