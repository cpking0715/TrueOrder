# 税号自动推荐冒烟：填品名 → 等chip → 点击回填
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\13-hs-auto.png")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/", wait_until="networkidle")
    page.get_by_label("产品名称").fill("女士棉质长裤")

    chip = page.locator("[data-testid='hs-auto-chip']")
    chip.wait_for(timeout=20000)
    text = chip.inner_text()
    print(f"chip: {text}")
    assert "6204" in text, text
    assert "验证" in text or "票" in text, text

    chip.click()
    filled = page.locator("[data-testid='quickstart-hs']").input_value()
    assert filled.startswith("6204"), filled
    print(f"filled: {filled}")
    page.screenshot(path=str(OUT))
    b.close()

print("HS_AUTO_SMOKE_OK")
