"""邮件发送端口与实现：SMTP（生产）/ Fake（测试）。"""

from __future__ import annotations

from typing import Protocol


class MailSender(Protocol):
    def send(
        self, *, to: str, subject: str, body: str,
        reply_to: str = "", unsubscribe_header: str = "",
    ) -> str:
        """发送邮件，返回 Message-ID 头。失败抛异常。"""
        ...


class FakeMailSender:
    """测试用：不实际发送，返回假 Message-ID。"""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(
        self, *, to: str, subject: str, body: str,
        reply_to: str = "", unsubscribe_header: str = "",
    ) -> str:
        message_id = f"<fake-{len(self.sent) + 1}@localhost>"
        self.sent.append({
            "to": to, "subject": subject, "body": body,
            "reply_to": reply_to, "unsubscribe": unsubscribe_header,
            "message_id": message_id,
        })
        return message_id


class SmtpMailSender:
    """真实 SMTP 发送（smtplib，支持 STARTTLS/SSL）。"""

    def __init__(
        self,
        host: str,
        port: int = 587,
        user: str = "",
        password: str = "",
        security: str = "starttls",  # starttls | ssl | none
        from_address: str = "",
        from_name: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._security = security
        self._from = f"{from_name} <{from_address}>" if from_name else from_address

    def send(
        self, *, to: str, subject: str, body: str,
        reply_to: str = "", unsubscribe_header: str = "",
    ) -> str:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.utils import formatdate, make_msgid

        msg = MIMEMultipart("alternative")
        msg["From"] = self._from
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid()
        if reply_to:
            msg["Reply-To"] = reply_to
        if unsubscribe_header:
            msg["List-Unsubscribe"] = unsubscribe_header
        msg.attach(MIMEText(body, "plain", "utf-8"))

        if self._security == "ssl":
            server = smtplib.SMTP_SSL(self._host, self._port, timeout=30)
        else:
            server = smtplib.SMTP(self._host, self._port, timeout=30)
            if self._security == "starttls":
                server.starttls()
        try:
            if self._user:
                server.login(self._user, self._password)
            server.send_message(msg)
        finally:
            server.quit()
        return msg["Message-ID"]


def make_mail_sender(settings) -> MailSender:
    """有 SMTP 配置建 SmtpSender，否则 Fake（演示/测试）。"""
    if settings.smtp_host:
        return SmtpMailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            security=settings.smtp_security,
            from_address=settings.smtp_from_address,
            from_name=settings.smtp_from_name,
        )
    return FakeMailSender()
