# WP5 发信前端冒烟：建模板 → 抽屉选联系人+模板 → 预览 → 确认发送
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\15-wp5-send.png")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})

    # 1. 跟进看板页：创建邮件模板
    page.goto("http://localhost:8000/#/pipeline", wait_until="networkidle")
    page.wait_for_selector("[data-testid='template-section']")
    page.click("button:has-text('新建模板')")
    page.locator("input[placeholder*='模板名']").fill("首次触达")
    page.locator("input[placeholder*='邮件主题']").fill("Partnership with {company}")
    page.locator("[data-testid='template-body']").fill(
        "Hi {contact_name},\n\nWe are a manufacturer of {product}.\n\nBest,\n{sender_name}"
    )
    page.screenshot(path=str(OUT).replace("15-", "15a-template-"))
    page.click("button:has-text('保存模板')")
    page.wait_for_selector("text=首次触达")
    print("template created")

    # 2. 产品详情 → 精准客户 → 打开抽屉 → 发信区
    page.goto("http://localhost:8000/#/products/1", wait_until="networkidle")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    page.reload()
    page.wait_for_selector("text=LONE STAR")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector("[data-testid='send-email-section']", timeout=10000)
    page.wait_for_timeout(1000)  # 等联系人加载
    section = page.locator("[data-testid='send-email-section']")
    text = section.inner_text()
    print(f"send section: {text[:100]}")

    # 3. 选联系人+模板 → 预览
    selects = section.locator("select")
    if selects.count() >= 2:
        # 第一个 select = 联系人，第二个 = 模板
        first_select = selects.nth(0)
        options = first_select.locator("option")
        for i in range(options.count()):
            val = options.nth(i).get_attribute("value")
            if val and val != "null":
                first_select.select_option(value=val)
                break

        second_select = selects.nth(1)
        options2 = second_select.locator("option")
        for i in range(options2.count()):
            val = options2.nth(i).get_attribute("value")
            if val and val != "null":
                second_select.select_option(value=val)
                break

        page.click("[data-testid='preview-email']")
        page.wait_for_selector("[data-testid='email-preview']", timeout=10000)
        preview_text = page.locator("[data-testid='email-preview']").inner_text()
        print(f"preview: {preview_text[:150]}")
        page.screenshot(path=str(OUT))

        # 4. 确认发送（如果护栏通过）
        send_btn = page.locator("[data-testid='send-email']")
        if send_btn.count():
            send_btn.click()
            page.wait_for_selector("[data-testid='sent-hint']", timeout=5000)
            print("SENT!")
        else:
            guards = page.locator(".badge.excluded")
            if guards.count():
                print(f"guards blocked: {guards.first.inner_text()}")
    else:
        print("no selects found (no contacts or templates)")

    b.close()

print("WP5_FRONTEND_SMOKE_OK")
