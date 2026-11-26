# Backend + built website in one container (Render, Railway, Hugging Face Spaces, any Docker host)
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
COPY backend/ backend/
COPY models/ models/
COPY --from=web /web/dist frontend/dist
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT}"]
