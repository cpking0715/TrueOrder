# 冒烟：填产品 → 找客户 的新主链路（e2e，浏览器有记录）
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\07-quickstart-flow.png")

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # 1. 首页应是「填产品找客户」表单
    page.goto("http://localhost:8000/#/", wait_until="networkidle")
    assert page.get_by_text("填你的产品，找对应客户").is_visible(), "首页主入口未生效"

    # 2. 填产品提交（买家词给行业词，验证精准层）
    page.get_by_label("产品名称").fill("儿童棉质运动套装")
    page.get_by_label("HS 税号").fill("620462")
    page.get_by_label("买家行业词（选填）").fill("APPAREL; CLOTHING")
    page.screenshot(path=str(OUT).replace("07-quickstart-flow", "07a-quickstart-form"))
    page.get_by_role("button", name="找客户").click()

    # 3. 应直接落到该产品的客户结果页
    page.wait_for_url("**/#/products/*")
    page.wait_for_selector("text=精准客户")
    tabs = page.get_by_role("tab").all_inner_texts()
    counts_text = " | ".join(t.strip() for t in tabs)
    assert any("精准客户（1" in t for t in tabs), f"精准计数异常：{counts_text}"
    assert any("潜在客户（2" in t for t in tabs), f"潜设计数异常：{counts_text}"
    page.screenshot(path=str(OUT))
    print("url:", page.url)
    print("tabs:", counts_text)
    browser.close()

print(f"saved: {OUT}")
