# OpsGenie AI — single-service image: FastAPI serves the API and the built
# React app from one origin. Models are trained at build time (they are
# gitignored) and the database seeds itself on first start.
#
#   docker build -t opsgenie-ai .
#   docker run -p 8000:8000 opsgenie-ai      ->  http://localhost:8000

# --- 1. build the frontend ---------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
# VITE_API_BASE_URL stays unset: the app calls /api on its own origin.
RUN npm run build

# --- 2. backend + trained models + static UI ---------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY data/ data/
WORKDIR /app/backend
RUN python -m app.ml.train_all
COPY --from=web /web/dist /app/backend/static
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
