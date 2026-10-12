# 第二轮修复复审：粘性头/锚点/折叠/动作区/漏斗/锁滚动
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/#/", wait_until="networkidle")
    checks = []
    funnel = page.locator("p.eyebrow").first.inner_text()
    checks.append(("D3 首页四步漏斗", "01 填产品" in funnel and "04 导出" in funnel))

    page.goto("http://localhost:8000/#/products/1", wait_until="networkidle")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    actions = page.evaluate("""() => {
      const box = document.querySelector('.detail-actions');
      return box && box.querySelectorAll('a.btn').length === 2;
    }""")
    checks.append(("D2 动作区含双导出", bool(actions)))

    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector(".drawer-head")
    checks.append(("D1 粘性头+锚点", page.locator(".drawer-head .drawer-nav a").count() == 4))
    checks.append(("D11 锁滚动", page.evaluate("() => document.body.style.overflow === 'hidden'")))
    # 关闭：滚动解锁 + 焦点回归
    page.keyboard.press("Escape")
    page.wait_for_selector("[data-testid='company-drawer']", state="detached")
    checks.append(("D11 解锁+焦点回归", page.evaluate(
        "() => document.body.style.overflow === '' && document.activeElement !== document.body")))
    # 联系人头部结构（h3 语义干净）
    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector(".contacts-head")
    h3 = page.evaluate("() => document.querySelector('.contacts-head h3').textContent.trim()")
    checks.append(("h3 语义干净", h3 == "联系人（1）"))
    b.close()

failed = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(("PASS " if ok else "FAIL ") + n)
print("ROUND2_" + ("OK" if not failed else "FAILED"))
