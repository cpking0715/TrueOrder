"""出海包领域规则：任务日历、产品档案校验、买家行清洗（零 mock）。"""

from __future__ import annotations

from datetime import date

from app.domain.kit import (
    KIT_PAGES,
    KIT_TASKS,
    ProductProfileInput,
    can_feature,
    clean_buyer_rows,
    current_day,
    tasks_for_day,
    validate_profile,
)


def test_14_天每天至少一个任务且页面键合法_任务键唯一():
    assert {t.day for t in KIT_TASKS} == set(range(1, 15))
    assert all(t.page in KIT_PAGES for t in KIT_TASKS)
    assert len({t.key for t in KIT_TASKS}) == len(KIT_TASKS)
    assert tasks_for_day(8)[0].page == "drafts"


def test_当前天数_未开始为1_超期封顶14():
    start = date(2026, 10, 1)
    assert current_day(None, start) == 1
    assert current_day(start, date(2026, 9, 30)) == 1
    assert current_day(start, date(2026, 10, 3)) == 3
    assert current_day(start, date(2026, 12, 1)) == 14


def _profile(**kw) -> ProductProfileInput:
    base = dict(
        image_url="https://img.example.com/a.jpg",
        specs="100% cotton",
        moq=300,
        lead_time_days=30,
        selling_points=("OEKO-TEX",),
        featured=True,
    )
    base.update(kw)
    return ProductProfileInput(**base)


def test_产品档案校验():
    assert validate_profile(_profile()) == []
    assert validate_profile(_profile(image_url="ftp://x")) == ["图片地址必须是 http(s) 链接"]
    assert "MOQ 必须 ≥ 1" in validate_profile(_profile(moq=0))
    assert "交期必须在 1–365 天之间" in validate_profile(_profile(lead_time_days=400))
    assert "卖点最多 5 条" in validate_profile(_profile(selling_points=tuple("abcdef")))
    assert validate_profile(_profile(image_url="")) == []


def test_主推上限5个_已主推再保存不占名额():
    assert can_feature(4, False)
    assert not can_feature(5, False)
    assert can_feature(5, True)


def test_买家行清洗_去重_邮箱校验_标签取值():
    rows = [
        {"company_name": "Tiny Steps LLC", "country": "USA", "email": "Buyer@TinySteps.com"},
        {"company_name": "Tiny Steps LLC", "country": "US", "email": "buyer@tinysteps.com"},
        {"company_name": "No Mail Kids", "country": "DE", "email": ""},
        {"company_name": "No Mail Kids", "country": "Germany", "email": ""},
        {"company_name": "Bad Mail", "country": "US", "email": "not-an-email"},
        {"company_name": "", "country": "US"},
        {"company_name": "Nowhere", "country": ""},
        {"company_name": "Odd", "country": "US", "channel": "fax"},
        {"company_name": "Wa Kids", "country": "AE", "channel": "WhatsApp", "stage": "replied"},
    ]
    r = clean_buyer_rows(rows)
    assert [b.company_name for b in r.valid] == ["Tiny Steps LLC", "No Mail Kids", "Wa Kids"]
    assert r.valid[0].email == "buyer@tinysteps.com" and r.valid[0].country == "US"
    assert r.valid[2].channel == "whatsapp" and r.valid[2].stage == "replied"
    assert r.valid[1].stage == "new" and r.valid[1].channel == "email"
    assert r.duplicates == 2
    assert len(r.errors) == 4
    assert r.errors[0].startswith("第 6 行：邮箱格式非法")
