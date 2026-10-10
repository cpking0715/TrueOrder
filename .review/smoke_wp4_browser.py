# WP4 浏览器段：抽屉展示补全得到的联系人（数据段已真实入队+worker 消费）
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\09-wp4-enrich.png")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/#/products/4", wait_until="networkidle")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    page.get_by_text("BROOKLYN APPAREL LLC").click()
    page.wait_for_selector("[data-testid='contacts-panel']")
    panel = page.locator("[data-testid='contacts-panel']").inner_text()
    assert "sales@brooklynapparel.example" in panel, f"联系人未出现：{panel}"
    assert "finder" in panel, f"来源标签缺失：{panel}"
    website = page.locator("[data-testid='website-field']").inner_text()
    assert "已确认" in website, website
    page.screenshot(path=str(OUT))
    browser.close()

print(f"saved: {OUT}")
print("WP4_BROWSER_OK")
