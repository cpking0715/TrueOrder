"""send_email 处理器：护栏结构化分支、额度延期不标失败、sending 幂等、SMTP 失败重试。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.jobs import QuotaDeferred, SqlJobQueue, Worker
from app.infrastructure.mail import FakeMailSender
from app.infrastructure.orm import (
    CompanyORM,
    ContactORM,
    EmailMessageORM,
    OpportunityORM,
    ProductORM,
    SuppressionORM,
)
from app.infrastructure.outreach import make_send_email_handler

NOW = datetime.now(UTC) + timedelta(hours=1)
CFG = Settings(
    company_address="1 Main St, Springfield, US",
    smtp_reply_to="reply@myco.com",
    smtp_daily_cap=30,
    _env_file=None,
)


@pytest.fixture()
def msg(session: Session) -> EmailMessageORM:
    product = ProductORM(code="P-T", name="T", buyer_type="importer")
    company = CompanyORM(normalized_name="ACME", country="US", name_variants=["Acme"])
    session.add_all([product, company])
    session.flush()
    contact = ContactORM(
        company_id=company.id, email="buyer@acme.com", source="finder",
        source_ref="hunter:domain-search",
    )
    opp = OpportunityORM(product_id=product.id, company_id=company.id)
    session.add_all([contact, opp])
    session.flush()
    m = EmailMessageORM(
        opportunity_id=opp.id, contact_id=contact.id, subject="Hi", body="Hello"
    )
    session.add(m)
    session.commit()
    return m


def _run(session, message_id, sender, cfg=CFG):
    make_send_email_handler(sender, cfg)(session, {"message_id": message_id})
    session.refresh(session.get(EmailMessageORM, message_id))
    return session.get(EmailMessageORM, message_id)


def test_正常发送_页脚带地址与退订(session, msg):
    sender = FakeMailSender()
    m = _run(session, msg.id, sender)
    assert m.status == "sent" and m.attempts == 1
    assert sender.sent[0]["body"].endswith("1 Main St, Springfield, US")
    assert sender.sent[0]["unsubscribe"] == "<mailto:reply@myco.com>"


def test_已发送重入不重发(session, msg):
    sender = FakeMailSender()
    _run(session, msg.id, sender)
    _run(session, msg.id, sender)
    assert len(sender.sent) == 1


def test_sending状态重入不重发并标人工核对(session, msg):
    msg.status = "sending"
    session.commit()
    sender = FakeMailSender()
    m = _run(session, msg.id, sender)
    assert sender.sent == []
    assert m.status == "failed" and "人工核对" in m.error


def test_SMTP失败标failed并抛出_重试后成功(session, msg):
    class Flaky(FakeMailSender):
        def __init__(self):
            super().__init__()
            self.fail_once = True

        def send(self, **kw):
            if self.fail_once:
                self.fail_once = False
                raise ConnectionError("smtp down")
            return super().send(**kw)

    sender = Flaky()
    with pytest.raises(ConnectionError):
        make_send_email_handler(sender, CFG)(session, {"message_id": msg.id})
    m = session.get(EmailMessageORM, msg.id)
    session.refresh(m)
    assert m.status == "failed" and "smtp down" in m.error
    m = _run(session, msg.id, sender)
    assert m.status == "sent" and len(sender.sent) == 1


def test_额度用尽延期且邮件保持queued(session, msg):
    cfg = Settings(**{**CFG.model_dump(), "smtp_daily_cap": 0}, _env_file=None)
    with pytest.raises(QuotaDeferred):
        make_send_email_handler(FakeMailSender(), cfg)(session, {"message_id": msg.id})
    session.rollback()
    m = session.get(EmailMessageORM, msg.id)
    session.refresh(m)
    assert m.status == "queued"


def test_额度用尽经worker延期_任务回pending(session, msg):
    cfg = Settings(**{**CFG.model_dump(), "smtp_daily_cap": 0}, _env_file=None)
    queue = SqlJobQueue(session)
    job_id = queue.enqueue("send_email", {"message_id": msg.id})
    Worker(queue, {"send_email": make_send_email_handler(FakeMailSender(), cfg)}).run_once(NOW)
    job = [j for j in queue.list_jobs() if j.id == job_id][0]
    assert job.status == "pending" and job.attempts == 0
    assert session.get(EmailMessageORM, msg.id).status == "queued"


def test_抑制名单标suppressed(session, msg):
    session.add(SuppressionORM(email="buyer@acme.com", reason="manual"))
    session.commit()
    sender = FakeMailSender()
    m = _run(session, msg.id, sender)
    assert m.status == "suppressed" and sender.sent == []


def test_缺来源记录标failed(session, msg):
    contact = session.get(ContactORM, msg.contact_id)
    contact.source_ref = ""
    session.commit()
    m = _run(session, msg.id, FakeMailSender())
    assert m.status == "failed" and "来源" in m.error


def test_缺发件配置标failed(session, msg):
    cfg = Settings(**{**CFG.model_dump(), "company_address": ""}, _env_file=None)
    m = _run(session, msg.id, FakeMailSender(), cfg)
    assert m.status == "failed" and "COMPANY_ADDRESS" in m.error
