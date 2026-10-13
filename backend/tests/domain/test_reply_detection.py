"""回复识别领域规则测试（纯函数）。"""

from __future__ import annotations

from app.domain.reply_detection import ReplyKind, classify_reply


def _cls(**kw):
    defaults = dict(
        sender_email="buyer@acme.com", subject="Re: Partnership",
        body="Thanks for reaching out.", in_reply_to="<abc@me>",
    )
    defaults.update(kw)
    return classify_reply(**defaults)


class Test正常回信:
    def test_普通回信分类为REPLY(self):
        r = _cls()
        assert r.kind == ReplyKind.REPLY
        assert r.matched_message_id == "<abc@me>"
        assert not r.should_suppress

    def test_含意向词推进阶段(self):
        r = _cls(body="We are interested in your pricing and catalog")
        assert r.kind == ReplyKind.REPLY
        assert r.should_advance_stage

    def test_不含意向词不推进(self):
        r = _cls(body="Not for us, thanks")
        assert not r.should_advance_stage


class Test退订:
    def test_正文含unsubscribe(self):
        r = _cls(body="Please unsubscribe me from your list")
        assert r.kind == ReplyKind.UNSUBSCRIBE
        assert r.should_suppress
        assert not r.should_mark_bounced

    def test_中文退订关键词(self):
        r = _cls(subject="退订", body="请退订")
        assert r.kind == ReplyKind.UNSUBSCRIBE


class Test退信:
    def test_MailerDaemon发件人(self):
        r = _cls(
            sender_email="mailer-daemon@mail.acme.com",
            subject="Delivery Status Notification",
        )
        assert r.kind == ReplyKind.BOUNCE
        assert r.should_suppress
        assert r.should_mark_bounced


class Test自动回复:
    def test_OutOfOffice(self):
        r = _cls(subject="Out of Office: Partnership")
        assert r.kind == ReplyKind.AUTO_REPLY
        assert not r.should_advance_stage
        assert not r.should_suppress


class TestReferences头:
    def test_从References取最近的(self):
        r = _cls(
            in_reply_to=None,
            references="<old@me> <mid@me> <new@me>",
        )
        assert r.matched_message_id == "<new@me>"

    def test_无References返回None(self):
        r = _cls(in_reply_to=None, references=None)
        assert r.matched_message_id is None
