"""商机阶段机（DEV-SPEC 3.3）：转换合法性、lost 规则、自动推进、到期判断。纯函数。"""

from __future__ import annotations

from datetime import date
from typing import Literal

Stage = Literal["lead", "contacted", "replied", "sample_quote", "negotiating", "won_intent", "lost"]
Intent = Literal["cold", "warm", "hot"]

# 有序阶段：前进 = 沿此序列向前跳（允许跳级）；lost 为独立终态
STAGES: tuple[str, ...] = (
    "lead", "contacted", "replied", "sample_quote", "negotiating", "won_intent",
)
TERMINAL_STAGES = ("won_intent", "lost")


def can_transition(from_stage: str, to_stage: str) -> bool:
    """合法转换：沿有序阶段前进（可跳级）；任意→lost；lost→lead 重开。"""
    if from_stage == to_stage:
        return False
    if to_stage == "lost":
        return from_stage != "lost"
    if from_stage == "lost":
        return to_stage == "lead"  # 重开回起点
    if from_stage == "won_intent":
        return False  # 成交意向后只能进 lost
    if from_stage in STAGES and to_stage in STAGES:
        return STAGES.index(to_stage) > STAGES.index(from_stage)
    return False


def validate_transition(from_stage: str, to_stage: str, closed_reason: str = "") -> str | None:
    """返回 None 表示合法；否则返回错误描述（422 用）。"""
    if to_stage == "lost" and from_stage != "lost" and not closed_reason.strip():
        return "进入 lost 必须填写 closed_reason（关闭原因）"
    if not can_transition(from_stage, to_stage):
        return f"不允许的阶段转换：{from_stage} → {to_stage}"
    return None


def auto_advance_on_email_sent(stage: str) -> str | None:
    """首封邮件成功发出且阶段为 lead → contacted（每次变更写 stage_change 活动）。"""
    return "contacted" if stage == "lead" else None


def auto_advance_on_email_in(stage: str) -> str | None:
    """记录收到回信且阶段为 contacted → replied。"""
    return "replied" if stage == "contacted" else None


def is_due(next_follow_up_on: date | None, stage: str, today: date) -> bool:
    """今日待跟进：到期日 ≤ 今天，且不在终态。"""
    if next_follow_up_on is None or stage in TERMINAL_STAGES:
        return False
    return next_follow_up_on <= today
