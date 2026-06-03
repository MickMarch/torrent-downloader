FROM python:3.12-slim

ARG APP_VERSION=0.0.0

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-cache --no-install-project

COPY src/ ./src/
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${APP_VERSION} uv sync --no-dev --frozen --no-cache

RUN useradd --no-create-home --shell /bin/false appuser && \
    mkdir -p /app/.cache && \
    chown -R appuser /app/.cache
USER appuser

EXPOSE 8000

CMD ["/app/.venv/bin/torrent-downloader"]
