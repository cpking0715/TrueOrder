# TrueOrder API + worker 共用镜像（Python 3.13，非 root 运行）
FROM python:3.13-slim

WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    TRUEORDER_SAMPLE_MODE=false

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /usr/local/bin/uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --locked --no-dev \
    && groupadd --system --gid 10001 trueorder \
    && useradd --system --uid 10001 --gid trueorder --home-dir /app --no-create-home trueorder \
    && mkdir -p /app/run && chown trueorder:trueorder /app/run

# 代码与虚拟环境归 root 只读；运行用户只可写 /app/run（worker 心跳等）
USER trueorder

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"]
# 默认起 API；worker 在 compose 里覆盖 command 与 healthcheck
CMD ["uvicorn", "app.interface.main:app", "--host", "0.0.0.0", "--port", "8000"]
