# Ask Territory — container image. Small app; the only dependency is the
# Anthropic SDK used for the "AI Powered" chat.
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

# Non-root user for safety. Pinned UID 1000 so the host can chown the bind-mounted
# ./data directory to match (the app needs to write the SQLite WAL files).
RUN useradd -m -u 1000 appuser && chown -R appuser /app
USER appuser

# ANTHROPIC_API_KEY is supplied at runtime (compose / systemd / platform secret),
# never baked into the image. No key -> the chat shows offline; data panels work.
ENV PORT=8000 \
    MODEL=claude-haiku-4-5 \
    MAX_OUTPUT_TOKENS=500

EXPOSE 8000

# Simple healthcheck against the API.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://localhost:8000/api/health',timeout=4)" || exit 1

CMD ["python", "-m", "webapp.server"]
