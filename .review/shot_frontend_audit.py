# 前端全量截图：改版后所有页面含 WP1/WP3/WP4 新组件（设计走查基准）
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\frontend-audit")
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 1. 首页（检索单 + 产品卡 + 导入面板）
    page.goto(f"{BASE}/#/", wait_until="networkidle")
    page.screenshot(path=str(OUT / "01-home.png"), full_page=True)

    # 2. 详情页潜在页签（表格色轨 + 筛选 + EnrichBar）
    page.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    page.wait_for_selector("text=LONE STAR")
    page.screenshot(path=str(OUT / "02-detail-potential.png"), full_page=True)

    # 3. 抽屉全貌：官网字段+置信度/联系人面板(含查找按钮)/得分/提单
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector("[data-testid='contacts-panel']")
    page.screenshot(path=str(OUT / "03-drawer-full.png"))

    # 4. 批量补全两段式（估计态）
    page.keyboard.press("Escape")
    page.wait_for_selector("text=精准客户")
    page.wait_for_selector("[data-testid='enrich-bar']")
    page.locator("[data-testid='enrich-estimate']").click()
    page.wait_for_selector("[data-testid='enrich-estimate-text']")
    page.screenshot(path=str(OUT / "04-enrich-estimate.png"))

    # 5. 任务页
    page.goto(f"{BASE}/#/jobs", wait_until="networkidle")
    page.wait_for_selector("[data-testid='jobs-empty'], [data-testid='jobs-table']")
    page.screenshot(path=str(OUT / "05-jobs.png"))

    # 6/7. 移动端首页与抽屉
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(f"{BASE}/#/", wait_until="networkidle")
    mobile.screenshot(path=str(OUT / "06-mobile-home.png"), full_page=True)
    mobile.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    mobile.wait_for_selector("text=LONE STAR")
    mobile.get_by_text("LONE STAR CLOTHING CO").click()
    mobile.wait_for_selector("[data-testid='contacts-panel']")
    mobile.screenshot(path=str(OUT / "07-mobile-drawer.png"))
    mobile.close()

    browser.close()

for f in sorted(OUT.glob("*.png")):
    print(f.name, f.stat().st_size)
print("SHOTS_OK")
