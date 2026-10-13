# Hunter 注册：反检测 + Turnstile 等待
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots")
EMAIL = "1396920681@qq.com"

with sync_playwright() as p:
    # 反自动化检测
    b = p.chromium.launch(
        channel="chrome",
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
        ],
    )
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    # 移除 webdriver 标记
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    page = ctx.new_page()

    page.goto("https://hunter.io/users/sign_up", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(5000)

    # 处理 cookie
    cookie = page.locator("#onetrust-accept-btn-handler")
    if cookie.count():
        cookie.click()
        page.wait_for_timeout(1000)

    # 等 Turnstile 完成（最多 15 秒）
    for i in range(15):
        ts_val = page.locator("[name='cf-turnstile-response']").input_value()
        if ts_val:
            print(f"Turnstile completed after {(i+1)}s")
            break
        page.wait_for_timeout(1000)
    else:
        print("Turnstile NOT completed after 15s")

    # 填邮箱
    email = page.locator("input[name='user[email]'][type='email']")
    email.fill(EMAIL)
    page.wait_for_timeout(1000)

    # 点击 "Create account"（email-signup-form 里的，非 Google）
    btns = page.locator("#email-signup-form button").all()
    for btn in btns:
        text = (btn.inner_text() or "").strip()
        if "google" in text.lower():
            continue
        print(f"clicking: {text!r}")
        btn.click()
        break

    page.wait_for_timeout(5000)
    print(f"url: {page.url}")

    # 检查 Step 2
    first = page.locator("input[name='user[first_name]']")
    visible = first.is_visible()
    print(f"first_name visible: {visible}")
    page.screenshot(path=str(OUT / "14b-step2.png"))

    if visible:
        first.fill("King")
        page.locator("input[name='user[last_name']").fill("Chen")
        page.locator("input[name='user[password]']").fill("TrueOrder2026!")
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "14c-filled.png"))

        submit = page.locator("#signup_form button[type='submit']")
        if not submit.count():
            submit = page.locator("button:has-text('Create account'):not(:has-text('Google'))")
        if submit.count():
            submit.first.click()
            page.wait_for_timeout(8000)

        print(f"final url: {page.url}")
        page.screenshot(path=str(OUT / "14-result.png"))
        body = page.locator("body").inner_text()[:300]
        print(f"result: {body[:200]}")

    b.close()
