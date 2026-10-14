"""CSV 导入后台任务：上传原文暂存 job_uploads，worker 执行导入（含重打分），结果写 jobs.result。"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.infrastructure.contact_repository import SqlContactRepository
from app.infrastructure.importers import CsvImporter
from app.infrastructure.jobs import Handler, PermanentJobError, SqlJobQueue
from app.infrastructure.orm import JobUploadORM

ImportTarget = Literal["bills", "contacts", "products"]
TARGETS: tuple[str, ...] = ("bills", "contacts", "products")


def enqueue_import(
    session: Session,
    target: ImportTarget,
    filename: str,
    text: str,
    as_of: date | None = None,
) -> int:
    """暂存上传 + 入队 import_csv，同一事务提交；返回 job_id。

    导入本身按哈希/唯一键去重，可安全重跑；仍只给 2 次机会，避免大文件反复失败占用 worker。
    """
    upload = JobUploadORM(filename=filename[:255], content=text)
    session.add(upload)
    session.flush()
    payload: dict[str, Any] = {"target": target, "upload_id": upload.id, "filename": filename}
    if as_of is not None:
        payload["as_of"] = as_of.isoformat()
    # enqueue 内部 commit：上传与任务一起落库
    return SqlJobQueue(session).enqueue("import_csv", payload, max_attempts=2)


def make_import_csv_handler(today: Any = date.today) -> Handler:
    def handle(session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        target = payload.get("target")
        if target not in TARGETS:
            raise PermanentJobError(f"未知导入类型：{target}")
        upload = session.get(JobUploadORM, payload.get("upload_id"))
        if upload is None:
            raise PermanentJobError("上传暂存已不存在（可能已处理完成），请重新上传")
        text, filename = upload.content, upload.filename
        result: dict[str, Any]
        if target == "contacts":
            s = SqlContactRepository(session).import_csv(text, source_ref=filename)
            result = {
                "added": s.added,
                "duplicates": s.duplicates,
                "company_not_found": s.company_not_found,
                "invalid_rows": s.invalid_rows,
            }
        else:
            importer = CsvImporter(session)
            if target == "bills":
                as_of = date.fromisoformat(payload["as_of"]) if payload.get("as_of") else None
                summary, rescores = importer.import_bills(text, source_ref=filename, as_of=as_of)
            else:
                summary = importer.import_products(text, source=filename)
                # 产品目录变化可能影响既有得分（关键词），导入后重打分
                rescores = importer.rescore(today())
            result = {**summary.__dict__, "rescore": [r.__dict__ for r in rescores]}
        # 成功后删除暂存原文（失败则保留供重试）
        session.delete(upload)
        session.commit()
        return _jsonable(result)

    return handle


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value
