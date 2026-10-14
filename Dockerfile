# TrueOrder API + worker 共用镜像（Python 3.13）
FROM python:3.13-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    TRUEORDER_SAMPLE_MODE=false

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev

EXPOSE 8000
# 默认起 API；worker 在 compose 里覆盖 command
CMD ["uv", "run", "uvicorn", "app.interface.main:app", "--host", "0.0.0.0", "--port", "8000"]
