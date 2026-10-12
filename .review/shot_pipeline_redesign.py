# 看板重设计截图验证
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\12-pipeline-redesign.png")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/pipeline", wait_until="networkidle")
    page.wait_for_selector("[data-testid='col-lead']")
    page.wait_for_timeout(500)

    # 验证：卡片无 select（旧问题的根源），有推进/流失按钮
    selects_in_cards = page.locator(".card select").count()
    advance_btns = page.locator(".card button[title*='推进']").count()
    lost_btns = page.locator(".card button[title*='流失']").count()
    print(f"selects_in_cards={selects_in_cards} advance_btns={advance_btns} lost_btns={lost_btns}")

    # 验证：今日待跟进横幅
    due = page.locator("[data-testid='due-today']").count()
    print(f"due_today_banner={due}")

    # 验证：列头带计数圆角
    lead_col = page.locator("[data-testid='col-lead']").inner_text()
    print(f"lead_col: {lead_col[:60]}")

    # 验证：推进交互——点 BROOKLYN 的推进按钮
    card1 = page.locator("[data-testid='card-1']")
    if card1.count():
        btn = card1.locator("button[title*='推进']")
        if btn.count():
            btn.click()
            page.wait_for_timeout(800)
            replied_col = page.locator("[data-testid='col-contacted']").inner_text()
            print(f"after advance → contacted col: {replied_col[:80]}")

    page.screenshot(path=str(OUT), full_page=True)

    # 移动端验证
    mobile = b.new_page(viewport={"width": 390, "height": 844})
    mobile.goto("http://localhost:8000/#/pipeline", wait_until="networkidle")
    mobile.wait_for_selector("[data-testid='col-lead']")
    overflow = mobile.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    print(f"mobile_overflow={overflow}")
    mobile.screenshot(path=str(OUT).replace("12-", "12m-"))
    mobile.close()

    b.close()

print(f"saved: {OUT}")
print("PIPELINE_REDESIGN_OK")
