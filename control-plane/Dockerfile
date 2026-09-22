# Control-plane image (multi-stage).
# Build context must be the REPO ROOT (see docker-compose.yml) so the shared
# `shim/` package and the `frontend/` app are both in scope.

# --- Stage 1: build the React SPA ---
FROM node:20-slim AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# --- Stage 2: python runtime ---
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "sqlalchemy>=2.0" \
    "psycopg[binary]>=3.1" \
    "alembic>=1.13" \
    "httpx>=0.27" \
    "cryptography>=42.0" \
    "argon2-cffi>=23.1" \
    "pyotp>=2.9" \
    "pyjwt>=2.8"

COPY control-plane/app /app/app
COPY control-plane/alembic /app/alembic
COPY control-plane/alembic.ini /app/alembic.ini
COPY pritunl-shim/shim /app/shim
COPY --from=frontend /ui/dist /app/app/static

ENV PYTHONPATH=/app
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
