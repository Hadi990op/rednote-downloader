# RedNote Video Downloader — Docker image
# Python + Flask + yt-dlp + ffmpeg + gunicorn

FROM python:3.12-slim

# Install ffmpeg (required for video merging/processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Temp directory for downloads
RUN mkdir -p /tmp/rednote_downloads

# Expose the port gunicorn will run on
ENV PORT=80
EXPOSE 80

# Health check endpoint (for platform to detect if app is alive)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-80}/health')" || exit 1

# Run with gunicorn — 2 workers, bind to all interfaces on PORT (default 80)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-80} --workers 2 --timeout 120 app:app"]
