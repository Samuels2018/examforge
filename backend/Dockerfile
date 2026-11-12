FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir "uv>=0.5"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY samples ./samples
COPY alembic.ini ./
COPY migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    EXAMFORGE_ENVIRONMENT=prod \
    EXAMFORGE_DATABASE_URL=sqlite:////data/examforge.db \
    EXAMFORGE_UPLOAD_DIR=/data/uploads \
    EXAMFORGE_BACKUP_DIR=/data/backups \
    EXAMFORGE_OLLAMA_BASE_URL=http://ollama:11434

RUN mkdir -p /data/uploads /data/backups

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3).read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
