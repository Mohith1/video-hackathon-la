FROM python:3.11-slim

# Install system dependencies (ffmpeg for audio/video, libsndfile for librosa)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure local storage dirs exist (used as fallback when no S3 creds)
RUN mkdir -p local_uploads local_db

EXPOSE 8000

# Railway sets $PORT; default 8000 for local/Docker Compose
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
