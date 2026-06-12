# Ask Territory — container image. Stdlib-only app, so the image is tiny.
FROM python:3.11-slim

WORKDIR /app

# No third-party Python deps — everything is standard library.
COPY . /app

# Non-root user for safety. Pinned UID 1000 so the host can chown the bind-mounted
# ./data directory to match (the app needs to write the SQLite WAL files).
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

ENV PORT=8000 \
    OLLAMA_HOST=http://ollama:11434 \
    MODEL=qwen2.5:7b-instruct

EXPOSE 8000

# Simple healthcheck against the API.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/api/health',timeout=4)" || exit 1

CMD ["python", "-m", "webapp.server"]
