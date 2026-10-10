# WP4 全链路冒烟：抽屉「查找联系方式」→ worker 消费 → 联系人带来源出现（浏览器有记录）
import subprocess
import sys
import time
from pathlib import Path



BASE = "http://localhost:8000"
BACKEND = Path(r"D:\MyProjects\TrueOrder\backend")
URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"

# 前置：给演示产品 QUICK-0002 的精准客户造一个可补全的企业（有官网未确认）
sys.path.insert(0, str(BACKEND))
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.infrastructure.orm import CompanyORM  # noqa: E402

engine = create_engine(URL)
with Session(engine) as s:
    company = s.query(CompanyORM).filter(
        CompanyORM.normalized_name == "BROOKLYN APPAREL"
    ).one_or_none()
    if company is None:
        raise SystemExit("库里没有 BROOKLYN APPAREL，请先 bootstrap")
    company.website = "https://brooklynapparel.example"
    company.website_confirmed = True
    from sqlalchemy import text
    s.execute(text("DELETE FROM contacts WHERE company_id = :cid"), {"cid": company.id})
    s.execute(text("DELETE FROM enrichment_calls"))
    s.commit()
    company_id = company.id
print("company ready:", company_id)

# 通过 HTTP API 触发入队（与界面同一路径）
import json
import urllib.request

req = urllib.request.Request(
    f"http://localhost:8000/api/companies/{company_id}/find-contacts",
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    body = json.loads(resp.read())
print("job enqueued:", body)

# 真实 worker 进程消费
import subprocess

r = subprocess.run(
    [sys.executable, "-m", "app.worker", "--once"],
    cwd=BACKEND, capture_output=True, text=True, timeout=120,
)
print("worker rc:", r.returncode, (r.stdout or "").strip())

# 验证联系人已入库
with Session(engine) as s2:
    from app.infrastructure.contact_repository import SqlContactRepository
    rows = SqlContactRepository(s2).list_by_company(company_id)
    for c in rows:
        print("contact:", c.email, "| source:", c.source, "| ref:", c.source_ref)
    assert rows, "worker 未产出联系人"
print("DATA_OK")
# 数据段顺带跑 worker：先入队一个任务（直接 API 调用绕过浏览器）
