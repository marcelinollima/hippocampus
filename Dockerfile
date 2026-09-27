FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HIPPOCAMPUS_DATA_DIR=/data \
    HIPPOCAMPUS_HOST=0.0.0.0 \
    HIPPOCAMPUS_PORT=8765 \
    FASTEMBED_CACHE_PATH=/data/models

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd --create-home --uid 1000 app \
    && mkdir -p /data && chown app:app /data

USER app
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=4)"
CMD ["hippocampus", "serve"]
