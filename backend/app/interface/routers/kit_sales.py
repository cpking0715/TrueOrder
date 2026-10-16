"""出海包 v0.1（内部工具）：开发信工作台（只生成不发送）、询盘与报价/PI 导出。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.domain.kit_sales import (
    INQUIRY_LABELS,
    DraftContext,
    DraftWriter,
    QuoteLine,
    follow_up_dates,
    generate_draft,
    line_total,
    validate_inquiry_transition,
    validate_quote,
)
from app.domain.outreach import is_suppressed
from app.infrastructure.kit_llm import LlmDraftWriter
from app.infrastructure.kit_sales_repository import (
    DraftRow,
    InquiryRow,
    SqlKitSalesRepository,
)
from app.interface.deps import get_session
from app.interface.kit_pi import build_pi_pdf
from app.interface.schemas_kit import (
    KitDraftIn,
    KitDraftOut,
    KitInquiryIn,
    KitInquiryOut,
    KitInquiryPatchIn,
)

router = APIRouter(prefix="/api/kit", tags=["kit"])


def _repo(session: Session = Depends(get_session)) -> SqlKitSalesRepository:
    return SqlKitSalesRepository(session)


def get_draft_writer(
    settings: Settings = Depends(get_settings), session: Session = Depends(get_session)
) -> DraftWriter | None:
    """有 AI Key 用 LLM，没有返回 None（领域走确定性模板）；测试用 overrides 注入 fake。"""
    if not settings.ai_api_key:
        return None
    return LlmDraftWriter.from_settings(settings, session)


def _draft_out(d: DraftRow) -> KitDraftOut:
    upcoming = [x for x in d.follow_up_on if x >= date.today()]
    return KitDraftOut(**d.__dict__, next_follow_up=min(upcoming) if upcoming else None)


@router.post("/drafts", response_model=KitDraftOut, status_code=201)
def create_draft(
    payload: KitDraftIn,
    repo: SqlKitSalesRepository = Depends(_repo),
    writer: DraftWriter | None = Depends(get_draft_writer),
    settings: Settings = Depends(get_settings),
):
    parts = repo.draft_parts(payload.product_id, payload.company_id, payload.contact_id)
    if parts is None:
        raise HTTPException(
            status_code=404, detail="产品、买家或联系人不存在（或联系人不属于该买家）"
        )
    if not parts.has_profile:
        raise HTTPException(status_code=422, detail="请先在「产品档案」里补齐该产品的规格/MOQ/交期")
    # 沿用开发信护栏：勿联系 / 抑制名单的联系人连草稿也不生成
    if parts.do_not_contact:
        raise HTTPException(status_code=409, detail="该联系人已标记为勿联系")
    if parts.contact_email and is_suppressed(parts.contact_email, repo.suppression_dicts()):
        raise HTTPException(status_code=409, detail="该联系人邮箱或域名在抑制名单中")
    ctx = DraftContext(
        channel=payload.channel, company=parts.company_name, country=parts.country,
        contact_name=parts.contact_name, product=parts.product_name, specs=parts.specs,
        moq=parts.moq, lead_time_days=parts.lead_time_days,
        selling_points=parts.selling_points, sender_name=settings.smtp_from_name,
    )
    draft, source = generate_draft(ctx, writer)
    row = repo.save_draft(
        product_id=payload.product_id, company_id=payload.company_id,
        contact_id=payload.contact_id, channel=payload.channel, subject=draft.subject,
        body=draft.body, source=source, follow_up_on=list(follow_up_dates(date.today())),
    )
    return _draft_out(row)


@router.get("/drafts", response_model=list[KitDraftOut])
def list_drafts(repo: SqlKitSalesRepository = Depends(_repo)):
    return [_draft_out(d) for d in repo.list_drafts()]


@router.get("/drafts/{draft_id}/export.txt", response_class=PlainTextResponse)
def export_draft(draft_id: int, repo: SqlKitSalesRepository = Depends(_repo)):
    d = repo.get_draft(draft_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"草稿 {draft_id} 不存在")
    head = f"Subject: {d.subject}\n\n" if d.subject else ""
    return PlainTextResponse(
        head + d.body,
        headers={"Content-Disposition": f'attachment; filename="draft-{draft_id}.txt"'},
    )


# ---------- 询盘与报价 ----------


def _inquiry_out(r: InquiryRow) -> KitInquiryOut:
    total = line_total(QuoteLine(r.product_name, r.quantity, r.unit_price))
    return KitInquiryOut(**r.__dict__, status_label=INQUIRY_LABELS[r.status], total=total)


@router.post("/inquiries", response_model=KitInquiryOut, status_code=201)
def create_inquiry(payload: KitInquiryIn, repo: SqlKitSalesRepository = Depends(_repo)):
    errors = validate_quote(payload.quantity, payload.unit_price, payload.currency)
    if errors:
        raise HTTPException(status_code=422, detail="；".join(errors))
    iid = repo.create_inquiry(
        payload.company_id, payload.product_id, payload.quantity, payload.unit_price,
        payload.currency, payload.note,
    )
    row = repo.get_inquiry(iid) if iid is not None else None
    if row is None:
        raise HTTPException(status_code=404, detail="买家或产品不存在")
    return _inquiry_out(row)


@router.get("/inquiries", response_model=list[KitInquiryOut])
def list_inquiries(repo: SqlKitSalesRepository = Depends(_repo)):
    return [_inquiry_out(r) for r in repo.list_inquiries()]


@router.patch("/inquiries/{inquiry_id}", response_model=KitInquiryOut)
def update_inquiry(
    inquiry_id: int, payload: KitInquiryPatchIn, repo: SqlKitSalesRepository = Depends(_repo)
):
    row = repo.get_inquiry(inquiry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"询盘 {inquiry_id} 不存在")
    error = validate_inquiry_transition(row.status, payload.status)
    if error:
        raise HTTPException(status_code=422, detail=error)
    repo.set_status(inquiry_id, payload.status)
    updated = repo.get_inquiry(inquiry_id)
    assert updated is not None  # noqa: S101 - 刚写入，必然存在
    return _inquiry_out(updated)


@router.get("/inquiries/{inquiry_id}/pi.pdf")
def export_pi(
    inquiry_id: int,
    repo: SqlKitSalesRepository = Depends(_repo),
    settings: Settings = Depends(get_settings),
):
    row = repo.get_inquiry(inquiry_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"询盘 {inquiry_id} 不存在")
    pdf, number = build_pi_pdf(
        row, repo.company_country(row.company_id), settings.smtp_from_name,
        settings.company_address, date.today(),
    )
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{number}.pdf"'},
    )
