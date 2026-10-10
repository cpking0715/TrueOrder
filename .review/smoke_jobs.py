# WP3 冒烟：入队 → worker --once 消费 → 任务状态页可见结果（浏览器有记录）
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND = Path(r"D:\MyProjects\TrueOrder\backend")
sys.path.insert(0, str(BACKEND))

from sqlalchemy import text as sql_text  # noqa: E402

from app.infrastructure.db import make_engine, make_session_factory  # noqa: E402
from app.infrastructure.jobs import SqlJobQueue  # noqa: E402

URL = "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
factory = make_session_factory(make_engine(URL))

with factory() as session:
    session.execute(sql_text("DELETE FROM jobs"))  # 清冒烟旧数据
    session.commit()
    queue = SqlJobQueue(session)
    ok_id = queue.enqueue("find_contacts", {"company_id": 1, "smoke": True})
    bad_id = queue.enqueue("send_email", {"smoke": True})  # 无处理器 → 永久失败
    print("enqueued:", ok_id, bad_id)

# 真实 worker 进程消费一轮：WP4 前无处理器，两条都应到终态 failed（unknown kind）
r = subprocess.run(
    [sys.executable, "-m", "app.worker", "--once"],
    cwd=BACKEND,
    capture_output=True,
    text=True,
    timeout=60,
)
print("worker rc:", r.returncode, "|", (r.stdout or "").strip(), (r.stderr or "").strip()[-200:])

from playwright.sync_api import sync_playwright  # noqa: E402

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\08-jobs-page.png")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/jobs", wait_until="networkidle")
    page.wait_for_selector("[data-testid='jobs-table']")
    body = page.locator("[data-testid='jobs-table']").inner_text()
    assert "查找联系人" in body, f"任务类型未渲染：{body}"
    assert "unknown job kind" in body, f"失败原因未渲染：{body}"
    # 过滤按钮交互：done 为空 → 空态；回全部 → 表格恢复
    page.locator("[data-testid='job-filter-done']").click()
    page.wait_for_selector("[data-testid='jobs-empty']")
    page.locator("[data-testid='job-filter-all']").click()
    page.wait_for_selector("[data-testid='jobs-table']")
    page.screenshot(path=str(OUT))
    browser.close()

print(f"saved: {OUT}")
print("JOBS_SMOKE_OK")
