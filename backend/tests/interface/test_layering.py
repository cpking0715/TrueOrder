"""分层守卫：接口层不得直接依赖 ORM / SQLAlchemy 查询构造。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INTERFACE = Path(__file__).resolve().parents[2] / "app" / "interface"


@pytest.mark.parametrize("path", sorted(INTERFACE.rglob("*.py")), ids=lambda p: p.name)
def test_接口层不导入orm(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "app.infrastructure.orm" or node.module == "sqlalchemy":
                names = {a.name for a in node.names}
                if node.module == "sqlalchemy" and names <= {"text"}:
                    continue
                bad.append(f"{node.module}: {sorted(names)}")
    assert not bad, f"{path.name} 越层导入：{bad}"
