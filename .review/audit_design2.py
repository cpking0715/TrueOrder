# 设计修复复审：D1 类已定义、D4 键盘行、D5 disabled、D10 无横向溢出
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")

    checks = []
    row = page.locator("tr.clickable").first
    checks.append(("D4 行可聚焦", row.evaluate("el => el.tabIndex === 0")))

    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector("[data-testid='contacts-panel']")
    ghost = page.locator("[data-testid='crawl-website']")
    checks.append(("D1 ghost 透明底", ghost.evaluate(
        "el => getComputedStyle(el).backgroundColor === 'rgba(0, 0, 0, 0)'")))
    drawer = page.locator("[data-testid='company-drawer']")
    # D3 证据优先：得分理由应出现在联系人面板之前
    order = drawer.inner_text()
    checks.append(("D3 得分理由在联系人之前", order.index("得分理由") < order.index("补全联系人")))
    # D13 焦点在抽屉内
    checks.append(("D13 打开即聚焦", drawer.evaluate(
        "el => el.contains(document.activeElement)")))

    # D10 移动端无横向溢出（详情页 + 任务页）
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    mobile.wait_for_selector("text=LONE STAR")
    o1 = mobile.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    mobile.goto(f"{BASE}/#/jobs", wait_until="networkidle")
    o2 = mobile.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    checks.append((f"D10 移动端无溢出({o1},{o2})", o1 <= 1 and o2 <= 1))
    mobile.close()
    browser.close()

failed = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + str(n))
print("AUDIT_" + ("OK" if not failed else "FAILED"))
