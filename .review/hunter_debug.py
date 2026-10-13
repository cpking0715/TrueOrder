# 调试 Hunter 注册页面状态
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto("https://hunter.io/users/sign_up", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    inputs = page.locator("input[name='user[email]']").all()
    for i, inp in enumerate(inputs):
        itype = inp.get_attribute("type")
        vis = inp.is_visible()
        print(f"email input {i}: type={itype} visible={vis}")

    first = page.locator("input[name='user[first_name]']")
    print(f"first_name: visible={first.is_visible()}")

    cookie = page.locator("#onetrust-accept-btn-handler, button:has-text('Accept')")
    if cookie.count():
        print(f"cookie banner: {cookie.count()} found, clicking...")
        cookie.first.click()
        page.wait_for_timeout(1000)

    email = page.locator("input[name='user[email]'][type='email']")
    print(f"email after cookie: visible={email.is_visible()} count={email.count()}")

    page.screenshot(path=r"D:\Projects\TrueOrder\.review\screenshots\14-debug.png")
    b.close()
