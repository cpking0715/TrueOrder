"""导出 OpenAPI 文档供前端生成 TS 类型：uv run python -m app.export_openapi"""

from __future__ import annotations

import json
from pathlib import Path

from app.interface.main import app

OUT = Path(__file__).resolve().parents[1] / "openapi.json"

if __name__ == "__main__":
    OUT.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {OUT}")
