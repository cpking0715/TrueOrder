"""开发信路由（WP5）：模板 CRUD、预览、入队发送、消息日志、抑制名单。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.outreach import (
    UNSUBSCRIBE_LINE,
    check_send_guards,
    compose_email_body,
    render_template,
    validate_template,
)
from app.infrastructure.outreach_repository import (
    ContactRecord,
    DuplicateTemplateError,
    SqlOutreachRepository,
    TemplateRecord,
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


def _repo(session: Session = Depends(get_session)) -> SqlOutreachRepository:
    return SqlOutreachRepository(session)


def _tpl_out(t: TemplateRecord) -> TemplateOut:
    return TemplateOut(id=t.id, name=t.name, subject=t.subject, body=t.body, language=t.language)


def _render(
    repo: SqlOutreachRepository, template: TemplateRecord, opp_id: int, contact: ContactRecord
) -> tuple[str, str]:
    company, product = repo.company_and_product_names(opp_id)
    variables = {
        "company": company,
        "contact_name": contact.name,
        "product": product,
        "last_arrival": "",
        "shipments": "",
        "supplier": "",
        "sender_name": "Sales Team",
    }
    try:
        return (
            render_template(template.subject, variables),
            render_template(template.body, variables),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------- 模板 CRUD ----------


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(repo: SqlOutreachRepository = Depends(_repo)):
    return [_tpl_out(t) for t in repo.list_templates()]


@router.post("/templates", response_model=TemplateOut, status_code=201)
def create_template(payload: TemplateIn, repo: SqlOutreachRepository = Depends(_repo)):
    unknown = validate_template(payload.subject + " " + payload.body)
    if unknown:
        raise HTTPException(status_code=422, detail=f"模板含不支持的变量：{', '.join(unknown)}")
    try:
        t = repo.create_template(payload.name, payload.subject, payload.body, payload.language)
    except DuplicateTemplateError as exc:
        raise HTTPException(status_code=409, detail="同名模板已存在") from exc
    return _tpl_out(t)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(template_id: int, repo: SqlOutreachRepository = Depends(_repo)):
    if not repo.delete_template(template_id):
        raise HTTPException(status_code=404, detail="模板不存在")


# ---------- 预览与入队 ----------


@router.post("/preview", response_model=PreviewOut)
def preview(
    payload: PreviewIn,
    repo: SqlOutreachRepository = Depends(_repo),
    settings: Settings = Depends(get_settings),
):
    """渲染模板 + 护栏检查；返回预览结果（不发送）。"""
    template = repo.get_template(payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not repo.opportunity_exists(payload.opportunity_id):
        raise HTTPException(status_code=404, detail="商机不存在")
    contact = repo.get_contact(payload.contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="联系人不存在")

    subject, body = _render(repo, template, payload.opportunity_id, contact)
    guards_error = check_send_guards(
        company_address=settings.company_address,
        reply_to=settings.smtp_reply_to,
        email=contact.email,
        do_not_contact=contact.do_not_contact,
        verify_status=contact.verify_status,
        source=contact.source,
        source_ref=contact.source_ref,
        suppressions=repo.suppression_dicts(),
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
def queue_send(payload: QueueIn, repo: SqlOutreachRepository = Depends(_repo)):
    """入队发送（必须先预览确认）。"""
    try:
        template_id, opp_id, contact_id = (int(x) for x in payload.preview_token.split(":"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="preview_token 格式非法") from exc

    template = repo.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    contact = repo.get_contact(contact_id)
    if contact is None or not contact.email:
        raise HTTPException(status_code=422, detail="联系人无邮箱")

    subject, body = _render(repo, template, opp_id, contact)
    message_id = repo.queue_message(opp_id, contact_id, template_id, subject, body)
    return {"message_id": message_id, "status": "queued"}


# ---------- 消息日志 ----------


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    status: str | None = None,
    limit: int = 50,
    repo: SqlOutreachRepository = Depends(_repo),
):
    return [
        MessageOut(
            id=m.id,
            opportunity_id=m.opportunity_id,
            contact_id=m.contact_id,
            subject=m.subject[:80],
            status=m.status,
            error=m.error,
            sent_at=m.sent_at,
        )
        for m in repo.list_messages(status, limit)
    ]


# ---------- 抑制名单 ----------


@router.get("/suppressions", response_model=list[SuppressionOut])
def list_suppressions(repo: SqlOutreachRepository = Depends(_repo)):
    return [SuppressionOut(**vars(s)) for s in repo.list_suppressions()]


@router.post("/suppressions", response_model=SuppressionOut, status_code=201)
def add_suppression(payload: SuppressionIn, repo: SqlOutreachRepository = Depends(_repo)):
    if not payload.email and not payload.domain:
        raise HTTPException(status_code=422, detail="email 或 domain 至少填一个")
    return SuppressionOut(
        **vars(repo.add_suppression(payload.email, payload.domain, payload.reason))
    )


@router.delete("/suppressions/{suppression_id}", status_code=204)
def delete_suppression(suppression_id: int, repo: SqlOutreachRepository = Depends(_repo)):
    if not repo.delete_suppression(suppression_id):
        raise HTTPException(status_code=404, detail="抑制记录不存在")
