# 设计自查：新视觉下逐页截图（Playwright + 系统 Chrome 无头）
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\redesign")
OUT.mkdir(parents=True, exist_ok=True)

BASE = "http://localhost:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 1. 首页：检索单 hero + 产品列表
    page.goto(f"{BASE}/#/", wait_until="networkidle")
    page.screenshot(path=str(OUT / "01-home.png"))

    # 2. 成衣详情：潜在页签（色轨行 + 信号板页签）
    page.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    page.wait_for_selector("text=LONE STAR")
    page.screenshot(path=str(OUT / "02-detail-potential.png"))

    # 3. 精准页签 + 抽屉（Esc 关闭验证）
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    page.get_by_text("BROOKLYN APPAREL LLC").click()
    page.wait_for_selector("[data-testid='company-drawer']")
    page.screenshot(path=str(OUT / "03-drawer.png"))
    page.keyboard.press("Escape")
    assert page.query_selector("[data-testid='company-drawer']") is None, "Esc 未关闭抽屉"

    # 4. 排除页签（驳回红轨）
    page.get_by_role("tab").filter(has_text="已排除").click()
    page.wait_for_selector("text=EX_BANK")
    page.screenshot(path=str(OUT / "04-excluded.png"))

    # 5. 空结果指引：建一个没数据的产品
    page.goto(f"{BASE}/#/", wait_until="networkidle")
    page.get_by_label("产品名称").fill("无人机机身碳纤维板")
    page.get_by_label("HS 税号").fill("880622")
    page.get_by_role("button", name="找客户").click()
    page.wait_for_url("**/#/products/*")
    page.wait_for_selector("[data-testid='no-bills-hint']")
    page.screenshot(path=str(OUT / "05-empty-guidance.png"))

    # 6. 移动端宽度自查
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(f"{BASE}/#/", wait_until="networkidle")
    mobile.screenshot(path=str(OUT / "06-mobile-home.png"))
    mobile.close()

    browser.close()

for f in sorted(OUT.glob("*.png")):
    print(f.name, f.stat().st_size)
print("REDESIGN_SMOKE_OK")
