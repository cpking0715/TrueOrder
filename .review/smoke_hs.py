# 税号反查浏览器冒烟：首页表单 → 按品名查 → 列表 → 点选回填
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\11-hs-suggest.png")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/", wait_until="networkidle")
    page.get_by_label("产品名称").fill("女士棉质长裤")
    page.locator("[data-testid='hs-suggest-open']").click()
    page.locator("[data-testid='hs-suggest-keyword']").fill("COTTON TROUSERS")
    page.screenshot(path=str(OUT).replace("11-hs", "11a-hs-input"))
    page.locator("[data-testid='hs-suggest-search']").click()
    page.wait_for_selector("[data-testid='hs-suggest-list']")
    lst = page.locator("[data-testid='hs-suggest-list']").inner_text()
    assert "620462" in lst and "票" in lst, lst[:200]
    page.locator("[data-testid='hs-pick-620462']").click()
    filled = page.locator("[data-testid='quickstart-hs']").input_value()
    assert filled == "620462", filled
    page.screenshot(path=str(OUT))
    b.close()
print("saved:", OUT)
print("HS_SUGGEST_SMOKE_OK")
