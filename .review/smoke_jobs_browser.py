# WP3 冒烟（浏览器段）：任务状态页渲染与过滤
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\08-jobs-page.png")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/jobs", wait_until="networkidle")
    page.wait_for_selector("[data-testid='jobs-table']")
    body = page.locator("[data-testid='jobs-table']").inner_text()
    assert "查找联系人" in body, f"任务类型未渲染：{body}"
    assert "unknown job kind" in body, f"失败原因未渲染：{body}"
    page.locator("[data-testid='job-filter-done']").click()
    page.wait_for_selector("[data-testid='jobs-empty']")
    page.locator("[data-testid='job-filter-all']").click()
    page.wait_for_selector("[data-testid='jobs-table']")
    page.screenshot(path=str(OUT))
    browser.close()
print(f"saved: {OUT}")
print("JOBS_SMOKE_OK")
