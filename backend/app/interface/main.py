"""FastAPI 入口：装配路由、CORS、可选的构建产物静态托管。"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.interface.routers import bills, contacts, enrich, jobs, meta, opportunities, products


def create_app() -> FastAPI:
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
    app.include_router(meta.router)
    app.include_router(products.router)
    app.include_router(bills.router)
    app.include_router(contacts.router)
    app.include_router(jobs.router)
    app.include_router(enrich.router)
    app.include_router(opportunities.router)

    _mount_frontend(app)
    return app


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
