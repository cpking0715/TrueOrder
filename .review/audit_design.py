# 设计自查（程序化）：关键计算样式、布局溢出、token 生效情况
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"

def contrast(fg: str, bg: str) -> float:
    def lum(c):
        c = c.lstrip("#")
        rgb = [int(c[i:i+2], 16) / 255 for i in (0, 2, 4)]
        rgb = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    l1, l2 = lum(fg), lum(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/#/", wait_until="networkidle")

    checks = []
    # 1. 顶栏：深墨底 + 海关青下边线
    topbar = page.locator(".topbar")
    checks.append(("topbar.bg=ink", topbar.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(19, 37, 60)"))
    # 2. 检索单表头条：深青底白字
    strip = page.locator(".strip")
    checks.append(("strip.bg=marine-deep", strip.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(10, 63, 69)"))
    # 3. HS 码位格：等宽 + 大字 + 字距
    hs = page.locator("[data-testid='quickstart-hs']")
    hs_style = hs.evaluate("el => { const s = getComputedStyle(el); return [s.fontFamily, s.fontSize, s.letterSpacing] }")
    checks.append(("hs-input.mono", "monospace" in hs_style[0] or "Cascadia" in hs_style[0] or "Consolas" in hs_style[0]))
    checks.append(("hs-input.21px", hs_style[1] == "21px"))
    # 4. 主按钮：海关青
    btn = page.get_by_role("button", name="找客户")
    checks.append(("btn.primary=marine", btn.evaluate("el => getComputedStyle(el).backgroundColor") == "rgb(14, 94, 102)"))
    # 5. 对比度：正文 ink #13253c on paper #ebf0f4；muted on panel
    checks.append(("contrast.ink/paper>=7", contrast("#13253c", "#ebf0f4") >= 7))
    checks.append(("contrast.muted/panel>=4.5", contrast("#5d6b7e", "#ffffff") >= 4.5))
    checks.append(("contrast.marine/white>=4.5", contrast("#0e5e66", "#ffffff") >= 4.5))

    # 详情页：色轨与页签色
    page.goto(f"{BASE}/#/products/1", wait_until="networkidle")
    page.wait_for_selector("text=LONE STAR")
    row = page.locator("tr.rail-potential").first
    checks.append(("row.rail=potential", row.count() >= 1))
    tab_precise = page.locator("[data-testid='tab-precise']")
    active_color = tab_precise.evaluate("el => getComputedStyle(el).color")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    active_after = tab_precise.evaluate("el => getComputedStyle(el).color")
    checks.append(("tab.precise.active=go-green", active_after == "rgb(23, 105, 74)" and active_color != active_after))
    precise_row = page.locator("tr.rail-precise").first
    checks.append(("row.rail.precise", precise_row.count() >= 1))

    # 移动端：无横向溢出
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(f"{BASE}/#/", wait_until="networkidle")
    overflow = mobile.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
    checks.append(("mobile.no-overflow", overflow <= 1))

    browser.close()

failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(("PASS " if ok else "FAIL ") + name)
print("AUDIT_" + ("OK" if not failed else "FAILED"))
