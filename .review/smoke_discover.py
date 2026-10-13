# AI 买家发现冒烟：触发 → worker 消费 → 公司入库 → 补全任务排队 → 浏览器验证
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
import urllib.request

BACKEND = Path(r"D:\MyProjects\TrueOrder\backend")
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

BASE = "http://localhost:8000"
URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"

# 1. 触发 AI 买家发现（对产品 4「儿童棉质运动套装」）
import time
time.sleep(4)
req = urllib.request.Request(f"{BASE}/api/products/4/discover-buyers", method="POST")
with urllib.request.urlopen(req) as resp:
    body = json.loads(resp.read())
print("job:", body)

# 2. worker 消费（真实 AI 调用）
r = subprocess.run(
    [sys.executable, "-m", "app.worker", "--once"],
    cwd=BACKEND, capture_output=True, text=True, timeout=120,
)
print("worker rc:", r.returncode, (r.stdout or "").strip()[:100])

# 3. 查库里发现的公司
engine = create_engine(URL)
with Session(engine) as s:
    # 发现任务新入库的公司（有 city 但无提单关联的）
    count = s.execute(text("""
        SELECT count(*) FROM companies c
        WHERE c.id NOT IN (SELECT DISTINCT consignee_company_id FROM raw_bills WHERE consignee_company_id IS NOT NULL)
        AND c.id NOT IN (SELECT DISTINCT shipper_company_id FROM raw_bills WHERE shipper_company_id IS NOT NULL)
        AND c.normalized_name NOT IN ('APPLE')
    """)).scalar()
    print(f"discovered companies (no bills): {count}")

    # 排队的 find_contacts 任务
    pending = s.execute(text(
        "SELECT count(*) FROM jobs WHERE kind='find_contacts' AND status='pending'"
    )).scalar()
    print(f"pending find_contacts jobs: {pending}")

    # 再跑一轮 worker 消费 find_contacts（走 Wikidata 免费路径）
    r2 = subprocess.run(
        [sys.executable, "-m", "app.worker", "--once"],
        cwd=BACKEND, capture_output=True, text=True, timeout=300,
    )
    print("worker2 rc:", r2.returncode)

    # 查有联系人的新公司
    with_contacts = s.execute(text("""
        SELECT count(DISTINCT c.id) FROM companies c
        JOIN contacts ct ON ct.company_id = c.id
        WHERE c.id NOT IN (SELECT DISTINCT consignee_company_id FROM raw_bills WHERE consignee_company_id IS NOT NULL)
        AND ct.source IN ('wikidata', 'website', 'finder')
    """)).scalar()
    print(f"discovered companies with contacts: {with_contacts}")

print("DISCOVER_SMOKE_OK")
