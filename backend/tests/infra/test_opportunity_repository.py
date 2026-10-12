"""商机仓储（真 PostgreSQL）：加入/幂等、阶段变更活动、到期过滤、时间线。"""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.opportunity_repository import (
    SqlOpportunityRepository,
    today_utc,
)
from app.infrastructure.orm import CompanyORM, ProductORM


@pytest.fixture()
def repo(session: Session) -> SqlOpportunityRepository:
    return SqlOpportunityRepository(session)


@pytest.fixture()
def product(session: Session) -> ProductORM:
    p = ProductORM(code="P-X", name="测试产品", buyer_type="importer")
    session.add(p)
    session.commit()
    return p


@pytest.fixture()
def company(session: Session) -> CompanyORM:
    c = CompanyORM(normalized_name="ACME", country="US", name_variants=["Acme LLC"])
    session.add(c)
    session.commit()
    return c


class Test加入跟进:
    def test_新建返回created并写note活动(self, repo, product, company):
        row, created = repo.add(product.id, company.id, owner_note="首批重点客户")
        assert created is True
        assert row.stage == "lead"
        assert row.company_name == "Acme LLC"
        timeline = repo.timeline(row.opportunity_id)
        assert timeline and timeline[0].kind == "note"

    def test_重复加入返回既有不新建(self, repo, product, company):
        first, created1 = repo.add(product.id, company.id)
        second, created2 = repo.add(product.id, company.id)
        assert created1 is True and created2 is False
        assert first.opportunity_id == second.opportunity_id
        assert len(repo.list_opportunities(product_id=product.id)) == 1


class Test阶段变更:
    def test_合法变更写stage_change活动(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        updated = repo.update(row.opportunity_id, stage="contacted")
        assert updated.stage == "contacted"
        timeline = repo.timeline(row.opportunity_id)
        assert timeline[0].kind == "stage_change"
        assert "lead → contacted" in timeline[0].summary

    def test_倒退被拒返回错误文本(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        repo.update(row.opportunity_id, stage="replied")
        result = repo.update(row.opportunity_id, stage="contacted")
        assert isinstance(result, str) and "不允许" in result

    def test_进lost缺原因被拒(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        result = repo.update(row.opportunity_id, stage="lost")
        assert isinstance(result, str) and "closed_reason" in result

    def test_进lost带原因存档且可重开(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        updated = repo.update(row.opportunity_id, stage="lost", closed_reason="预算冻结")
        assert updated.closed_reason == "预算冻结"
        reopened = repo.update(row.opportunity_id, stage="lead")
        assert reopened.stage == "lead"
        assert reopened.closed_reason is None  # 重开清原因


class Test列表与到期:
    def test_按阶段过滤(self, repo, product, company):
        a, _ = repo.add(product.id, company.id)
        repo.update(a.opportunity_id, stage="replied")
        assert len(repo.list_opportunities(stage="replied")) == 1
        assert len(repo.list_opportunities(stage="lead")) == 0

    def test_今日待跟进只含到期非终态(self, repo, product, company, session):
        a, _ = repo.add(product.id, company.id)
        today = today_utc()
        # a：昨天到期 → 待跟进
        repo.update(a.opportunity_id, next_follow_up_on=today - timedelta(days=1))
        other = CompanyORM(normalized_name="BETA", country="US", name_variants=["Beta"])
        session.add(other)
        session.commit()
        b, _ = repo.add(product.id, other.id)
        repo.update(b.opportunity_id, next_follow_up_on=today + timedelta(days=3))  # 未到期
        due = repo.list_opportunities(due_on=today)
        assert [r.opportunity_id for r in due] == [a.opportunity_id]
        # a 推进到 won_intent 后不再待跟进
        repo.update(a.opportunity_id, stage="won_intent")
        assert repo.list_opportunities(due_on=today) == []


class Test活动与时间线:
    def test_活动写意愿并回写商机(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        activity = repo.add_activity(
            row.opportunity_id, kind="call", summary="通了电话", intent_after="warm"
        )
        assert activity.kind == "call"
        assert repo.get(row.opportunity_id).intent == "warm"

    def test_非法活动类型被拒(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        result = repo.add_activity(row.opportunity_id, kind="smoke_signal", summary="x")
        assert result == "invalid_kind"

    def test_时间线倒序(self, repo, product, company):
        row, _ = repo.add(product.id, company.id)
        repo.add_activity(row.opportunity_id, kind="note", summary="第一")
        repo.add_activity(row.opportunity_id, kind="call", summary="第二")
        timeline = repo.timeline(row.opportunity_id)
        assert [t.summary for t in timeline][:2] == ["第二", "第一"]

    def test_不存在的时间线返回None(self, repo):
        assert repo.timeline(99999) is None
