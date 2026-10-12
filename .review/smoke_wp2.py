# WP2 商机管道浏览器冒烟：看板/换阶段/流失原因/抽屉跟进区/今日待跟进
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"D:\MyProjects\TrueOrder\.review\screenshots\10-wp2-pipeline.png")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page(viewport={"width": 1440, "height": 900})

    # 0. 幂等重置演示状态（本脚本第 3 步会改动阶段）
    page.request.patch(
        "http://localhost:8000/api/opportunities/1",
        data='{"stage": "lead"}',
        headers={"Content-Type": "application/json"},
    )

    # 1. 看板分列 + 今日待跟进横幅（NINGBO 到期日 2026-10-11 ≤ 今天）
    page.goto("http://localhost:8000/#/pipeline", wait_until="networkidle")
    page.wait_for_selector("[data-testid='col-lead']")
    assert "BROOKLYN APPAREL" in page.locator("[data-testid='col-lead']").inner_text()
    page.wait_for_selector("[data-testid='due-today']")
    assert "NINGBO WEAR" in page.locator("[data-testid='due-today']").inner_text()

    # 2. 换阶段：BROOKLYN lead → replied
    page.locator("[data-testid='stage-1']").select_option("replied")
    page.wait_for_timeout(600)
    assert "BROOKLYN APPAREL" in page.locator("[data-testid='col-replied']").inner_text()

    # 3. 流失需原因：先空原因被拒，填后成功
    page.locator("[data-testid='stage-1']").select_option("lost")
    page.wait_for_selector("[data-testid='lost-reason']")
    page.get_by_text("确认流失").click()
    page.wait_for_selector("text=流失必须填写原因")
    page.locator("[data-testid='lost-reason']").fill("无回复三个月")
    page.get_by_text("确认流失").click()
    page.wait_for_selector(".lost-panel")
    assert "无回复三个月" in page.locator(".lost-panel").inner_text()
    page.screenshot(path=str(OUT))
    page.request.patch(
        "http://localhost:8000/api/opportunities/1",
        data='{"stage": "lead"}',
        headers={"Content-Type": "application/json"},
    )

    # 4. 详情页：已加入商机的行显示阶段徽章（精准页签 BROOKLYN=线索），
    #    未加入的行是「加入跟进」按钮；抽屉跟进区显示备注与时间线
    page.goto("http://localhost:8000/#/products/1", wait_until="networkidle")
    page.get_by_role("tab").filter(has_text="精准客户").click()
    page.wait_for_selector("text=BROOKLYN")
    table = page.locator("[data-testid='buyers-table']").inner_text()
    assert "线索" in table, f"已加入商机应显示阶段徽章：{table[:200]}"
    page.get_by_text("BROOKLYN APPAREL LLC", exact=True).first.click()
    page.wait_for_selector("[data-testid='followup-section']")
    fu = page.locator("[data-testid='followup-section']").inner_text()
    assert "三票采购" in fu, fu[:200]
    # 记一条备注活动
    page.locator("[data-testid='activity-summary']").fill("发了目录，约下周通话")
    page.locator("[data-testid='activity-submit']").click()
    page.wait_for_selector("text=发了目录，约下周通话")

    b.close()

print(f"saved: {OUT}")
print("WP2_SMOKE_OK")
