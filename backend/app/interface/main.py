"""FastAPI 入口：装配路由、CORS、可选的构建产物静态托管。"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings, require_configured_database
from app.core.logging import configure_logging, get_logger, request_id_var
from app.interface.auth import require_api_token
from app.interface.deps import get_session
from app.interface.routers import (
    bills,
    contacts,
    enrich,
    hs,
    jobs,
    kit,
    kit_sales,
    meta,
    opportunities,
    outreach,
    products,
)

log = get_logger("app.api")


def create_app() -> FastAPI:
    configure_logging()
    require_configured_database()
    app = FastAPI(
        title="TrueOrder 自家产品海外买家库",
        version="0.1.0",
        description="以自家产品为入口，把授权海运提单聚成潜在/精准客户名单（样本期标注非全量）。",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _install_request_logging(app)

    if not get_settings().api_token:
        log.warning("TRUEORDER_API_TOKEN 未设置：API 鉴权关闭，仅限本机（127.0.0.1）开发使用")
    protected = [Depends(require_api_token)]
    app.include_router(meta.router, dependencies=protected)
    app.include_router(products.router, dependencies=protected)
    app.include_router(bills.router, dependencies=protected)
    app.include_router(contacts.router, dependencies=protected)
    app.include_router(jobs.router, dependencies=protected)
    app.include_router(enrich.router, dependencies=protected)
    app.include_router(opportunities.router, dependencies=protected)
    app.include_router(hs.router, dependencies=protected)
    app.include_router(outreach.router, dependencies=protected)
    app.include_router(kit.router, dependencies=protected)
    app.include_router(kit_sales.router, dependencies=protected)


    @app.get("/healthz", include_in_schema=False)
    def healthz(session: Session = Depends(get_session)):
        """存活 + 数据库连通检查（不鉴权、不含业务数据），供进程托管/负载均衡探活。"""
        try:
            session.execute(text("select 1"))
        except Exception:
            log.exception("healthz 数据库检查失败")
            return JSONResponse({"status": "error", "db": "down"}, status_code=503)
        return {"status": "ok", "db": "ok"}

    _mount_frontend(app)
    return app


def _install_request_logging(app: FastAPI) -> None:
    """每请求一个 request_id（沿用客户端 X-Request-ID），写入日志上下文与响应头。"""

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            raise
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        if request.url.path.startswith("/api"):
            log.info(
                "request",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - start) * 1000, 1),
                },
            )
        return response


def _mount_frontend(app: FastAPI) -> None:
    """存在构建产物时由后端直接托管（hash 路由，无需 SPA 回退）。"""
    # app/interface/main.py → 仓库根/frontend/dist
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not (dist / "index.html").exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(dist / "index.html")


app = create_app()
