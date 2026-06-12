# ============================================================
# IngeScan - Imagen Docker para despliegue en la nube
# Base ligera con PyTorch CPU + dependencias del sistema para OpenCV/YOLO
# ============================================================
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Dependencias del sistema necesarias para opencv-python-headless y ultralytics
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python primero para aprovechar el cache de capas
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copiar el código y el modelo
COPY . .

# Pre-crear directorios mutables
RUN mkdir -p static/uploads

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:${PORT}/health || exit 1

# Gunicorn con timeout amplio: la primera inferencia carga el modelo (lazy)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 120 app:app"]
