"""开发信路由（WP5）：模板 CRUD、预览、入队发送、消息日志、抑制名单。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.outreach import (
    UNSUBSCRIBE_LINE,
    check_send_guards,
    compose_email_body,
    render_template,
    validate_template,
)
from app.infrastructure.jobs import SqlJobQueue
from app.infrastructure.orm import (
    ContactORM,
    EmailMessageORM,
    EmailTemplateORM,
    OpportunityORM,
    SuppressionORM,
)
from app.interface.deps import get_session

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


# ---------- DTO ----------

class TemplateIn(BaseModel):
    name: str
    subject: str
    body: str
    language: str = "en"


class TemplateOut(BaseModel):
    id: int
    name: str
    subject: str
    body: str
    language: str


class PreviewIn(BaseModel):
    template_id: int
    opportunity_id: int
    contact_id: int


class PreviewOut(BaseModel):
    subject: str
    body: str
    guards_ok: bool
    guards_error: str | None = None


class QueueIn(BaseModel):
    preview_token: str  # 简化：直接用 "template_id:opportunity_id:contact_id"


class MessageOut(BaseModel):
    id: int
    opportunity_id: int
    contact_id: int | None
    subject: str
    status: str
    error: str | None
    sent_at: datetime | None


class SuppressionIn(BaseModel):
    email: str | None = None
    domain: str | None = None
    reason: str = "manual"


class SuppressionOut(BaseModel):
    id: int
    email: str | None
    domain: str | None
    reason: str


def _session_dep(session: Session = Depends(get_session)) -> Session:
    return session


# ---------- 模板 CRUD ----------

@router.get("/templates", response_model=list[TemplateOut])
def list_templates(session: Session = Depends(_session_dep)):
    return [
        TemplateOut(id=t.id, name=t.name, subject=t.subject, body=t.body, language=t.language)
        for t in session.scalars(select(EmailTemplateORM).order_by(EmailTemplateORM.id))
    ]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(payload: TemplateIn, session: Session = Depends(_session_dep)):
    unknown = validate_template(payload.subject + " " + payload.body)
    if unknown:
        raise HTTPException(status_code=422, detail=f"模板含不支持的变量：{', '.join(unknown)}")
    existing = session.scalar(
        select(EmailTemplateORM).where(EmailTemplateORM.name == payload.name)
    )
    if existing:
        raise HTTPException(status_code=409, detail="同名模板已存在")
    t = EmailTemplateORM(
        name=payload.name, subject=payload.subject, body=payload.body, language=payload.language
    )
    session.add(t)
    session.commit()
    return TemplateOut(id=t.id, name=t.name, subject=t.subject, body=t.body, language=t.language)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, session: Session = Depends(_session_dep)):
    t = session.get(EmailTemplateORM, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    session.delete(t)
    session.commit()


# ---------- 预览与入队 ----------

@router.post("/preview", response_model=PreviewOut)
def preview(
    payload: PreviewIn,
    session: Session = Depends(_session_dep),
    settings: Settings = Depends(get_settings),
):
    """渲染模板 + 护栏检查；返回预览结果（不发送）。"""
    template = session.get(EmailTemplateORM, payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    opp = session.get(OpportunityORM, payload.opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="商机不存在")
    contact = session.get(ContactORM, payload.contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="联系人不存在")

    from app.infrastructure.orm import CompanyORM, ProductORM

    company = session.get(CompanyORM, opp.company_id)
    product = session.get(ProductORM, opp.product_id)
    variables = {
        "company": company.normalized_name if company else "",
        "contact_name": contact.name or "",
        "product": product.name if product else "",
        "last_arrival": "",
        "shipments": "",
        "supplier": "",
        "sender_name": "Sales Team",
    }
    try:
        subject = render_template(template.subject, variables)
        body = render_template(template.body, variables)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    suppressions = [
        {"email": s.email, "domain": s.domain}
        for s in session.scalars(select(SuppressionORM))
    ]
    guards_error = check_send_guards(
        company_address=settings.company_address,
        reply_to=settings.smtp_reply_to,
        email=contact.email or "",
        do_not_contact=bool(contact.do_not_contact),
        verify_status=contact.verify_status,
        source=contact.source,
        source_ref=contact.source_ref,
        suppressions=suppressions,
        recent_sends=[],
        sent_today=0,
    )
    return PreviewOut(
        subject=subject,
        body=(
            compose_email_body(body, settings.company_address)
            if settings.company_address.strip()
            else body + UNSUBSCRIBE_LINE
        ),
        guards_ok=guards_error is None,
        guards_error=guards_error.message if guards_error else None,
    )


@router.post("/queue", status_code=202)
def queue_send(payload: QueueIn, session: Session = Depends(_session_dep)):
    """入队发送（必须先预览确认）。"""
    try:
        template_id, opp_id, contact_id = (int(x) for x in payload.preview_token.split(":"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="preview_token 格式非法") from exc

    template = session.get(EmailTemplateORM, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    contact = session.get(ContactORM, contact_id)
    if contact is None or not contact.email:
        raise HTTPException(status_code=422, detail="联系人无邮箱")

    from app.infrastructure.orm import CompanyORM, ProductORM

    opp = session.get(OpportunityORM, opp_id)
    company = session.get(CompanyORM, opp.company_id) if opp else None
    product = session.get(ProductORM, opp.product_id) if opp else None
    variables = {
        "company": company.normalized_name if company else "",
        "contact_name": contact.name or "",
        "product": product.name if product else "",
        "last_arrival": "", "shipments": "", "supplier": "",
        "sender_name": "Sales Team",
    }
    try:
        subject = render_template(template.subject, variables)
        body = render_template(template.body, variables)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    msg = EmailMessageORM(
        opportunity_id=opp_id,
        contact_id=contact_id,
        template_id=template_id,
        subject=subject,
        body=body,
    )
    session.add(msg)
    session.flush()
    queue = SqlJobQueue(session)
    queue.enqueue("send_email", {"message_id": msg.id})
    session.commit()
    return {"message_id": msg.id, "status": "queued"}


# ---------- 消息日志 ----------

@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(_session_dep),
):
    stmt = select(EmailMessageORM).order_by(EmailMessageORM.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(EmailMessageORM.status == status)
    return [
        MessageOut(
            id=m.id, opportunity_id=m.opportunity_id, contact_id=m.contact_id,
            subject=m.subject[:80], status=m.status, error=m.error, sent_at=m.sent_at,
        )
        for m in session.scalars(stmt)
    ]


# ---------- 抑制名单 ----------

@router.get("/suppressions", response_model=list[SuppressionOut])
def list_suppressions(session: Session = Depends(_session_dep)):
    return [
        SuppressionOut(id=s.id, email=s.email, domain=s.domain, reason=s.reason)
        for s in session.scalars(select(SuppressionORM).order_by(SuppressionORM.id))
    ]


@router.post("/suppressions", response_model=SuppressionOut, status_code=201)
def add_suppression(payload: SuppressionIn, session: Session = Depends(_session_dep)):
    if not payload.email and not payload.domain:
        raise HTTPException(status_code=422, detail="email 或 domain 至少填一个")
    s = SuppressionORM(
        email=payload.email, domain=payload.domain, reason=payload.reason
    )
    session.add(s)
    session.commit()
    return SuppressionOut(id=s.id, email=s.email, domain=s.domain, reason=s.reason)


@router.delete("/suppressions/{suppression_id}", status_code=204)
def delete_suppression(suppression_id: int, session: Session = Depends(_session_dep)):
    s = session.get(SuppressionORM, suppression_id)
    if s is None:
        raise HTTPException(status_code=404, detail="抑制记录不存在")
    session.delete(s)
    session.commit()
