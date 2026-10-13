"""WP6 IMAP 回复识别测试：分类→自动动作（阶段推进/抑制/bounced）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.infrastructure.imap_watcher import FakeImapInbox, make_poll_imap_handler
from app.infrastructure.orm import (
    ActivityORM,
    CompanyORM,
    ContactORM,
    EmailMessageORM,
    OpportunityORM,
    ProductORM,
    SuppressionORM,
)

NOW = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture()
def setup_sent_email(session: Session):
    """造一封已发送的邮件（带 Message-ID），返回 (contact, opp, message)。"""
    prod = ProductORM(code="T", name="Test", buyer_type="importer")
    session.add(prod)
    session.flush()
    company = CompanyORM(normalized_name="ACME", country="US", name_variants=["Acme"])
    session.add(company)
    session.flush()
    contact = ContactORM(
        company_id=company.id, name="John", title="Buyer",
        email="john@acme.com", source="manual", is_generic=False,
        verify_status="valid", do_not_contact=False,
    )
    session.add(contact)
    session.flush()
    opp = OpportunityORM(product_id=prod.id, company_id=company.id, stage="contacted")
    session.add(opp)
    session.flush()
    msg = EmailMessageORM(
        opportunity_id=opp.id, contact_id=contact.id,
        subject="Partnership", body="Hello",
        status="sent", sent_at=datetime.now(UTC),
        message_id_header="<sent-123@me>",
    )
    session.add(msg)
    session.commit()
    return contact, opp, msg


class Test正常回信:
    def test_有意向回信推进阶段并写活动(self, session, setup_sent_email):
        contact, opp, msg = setup_sent_email
        inbox = FakeImapInbox([{
            "sender": "john@acme.com", "subject": "Re: Partnership",
            "body": "We are interested in your pricing",
            "in_reply_to": "<sent-123@me>",
        }])
        handler = make_poll_imap_handler(inbox=inbox, settings=Settings())
        handler(session, {})

        session.expire_all()
        assert session.get(OpportunityORM, opp.id).stage == "replied"
        acts = session.query(ActivityORM).filter_by(opportunity_id=opp.id, kind="email_in").all()
        assert acts

    def test_无意向回信只记活动不推进(self, session, setup_sent_email):
        contact, opp, msg = setup_sent_email
        inbox = FakeImapInbox([{
            "sender": "john@acme.com", "subject": "Re: Partnership",
            "body": "Not for us thanks",
            "in_reply_to": "<sent-123@me>",
        }])
        handler = make_poll_imap_handler(inbox=inbox, settings=Settings())
        handler(session, {})

        session.expire_all()
        assert session.get(OpportunityORM, opp.id).stage == "contacted"  # 不推进
        acts = session.query(ActivityORM).filter_by(opportunity_id=opp.id).all()
        assert acts  # 但有活动记录


class Test退订:
    def test_退订写抑制名单(self, session, setup_sent_email):
        contact, opp, msg = setup_sent_email
        inbox = FakeImapInbox([{
            "sender": "john@acme.com", "subject": "Re: Partnership",
            "body": "Please unsubscribe me",
            "in_reply_to": "<sent-123@me>",
        }])
        handler = make_poll_imap_handler(inbox=inbox, settings=Settings())
        handler(session, {})

        session.expire_all()
        supp = session.query(SuppressionORM).filter_by(email="john@acme.com").first()
        assert supp is not None
        assert supp.reason == "unsubscribed"


class Test退信:
    def test_退信标bounced并写抑制(self, session, setup_sent_email):
        contact, opp, msg = setup_sent_email
        inbox = FakeImapInbox([{
            "sender": "mailer-daemon@mail.acme.com",
            "subject": "Delivery Status Notification (Failure)",
            "body": "Address not found",
            "in_reply_to": "<sent-123@me>",
        }])
        handler = make_poll_imap_handler(inbox=inbox, settings=Settings())
        handler(session, {})

        session.expire_all()
        assert session.get(ContactORM, contact.id).verify_status == "bounced"
        supp = session.query(SuppressionORM).filter_by(email="mailer-daemon@mail.acme.com").first()
        assert supp is not None
        assert supp.reason == "bounced"


class Test边界:
    def test_无法关联的邮件跳过(self, session, setup_sent_email):
        inbox = FakeImapInbox([{
            "sender": "random@x.com", "subject": "Spam",
            "body": "Buy now", "in_reply_to": "<unknown@me>",
        }])
        handler = make_poll_imap_handler(inbox=inbox, settings=Settings())
        handler(session, {})  # 不应报错
        assert session.query(SuppressionORM).count() == 0

    def test_未配置SMTP跳过(self, session):
        handler = make_poll_imap_handler(settings=Settings())
        handler(session, {})  # 无 inbox 且无 SMTP 配置 → 直接返回
