"""应用配置：环境变量 + .env（pydantic-settings），凭据不进源码。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRUEORDER_", env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
    )
    # API 访问令牌：设置后所有 /api 路由必须带令牌；空 = 关闭鉴权（仅限本机开发/演示）
    api_token: str = ""
    # CSV 上传上限（MB）：产品与提单导入端点共用，超出返回 413
    max_upload_mb: int = 20
    # WP4 补全：Hunter API Key（空 = 走 fake 演示数据并在界面提示）
    hunter_api_key: str = ""
    # 按次补全每日调用上限（合规约束：禁止无人触发的全库自动补全）
    enrich_daily_cap: int = 20
    # AI 增强提取（官网联系人结构化）：DeepSeek OpenAI 兼容接口
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-flash"
    ai_daily_cap: int = 200  # AI 调用每日上限（同样仅用户触发，记审计）
    # WP5 SMTP 发信（不配走 Fake 演示发送器）
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_security: str = "starttls"  # starttls | ssl | none
    smtp_from_address: str = ""
    smtp_from_name: str = ""
    smtp_reply_to: str = ""
    smtp_daily_cap: int = 30  # 每日发送上限（合规硬约束，不可界面关闭）
    smtp_cooldown_days: int = 3  # 同一联系人两封间隔最小天数
    company_address: str = ""  # 合规必填：公司物理地址（缺则拒绝发送）
    # 样本声明：界面必须展示「非全量库」
    sample_notice: str = (
        "当前库内为公开样本数据（非全量样本）：仅用于演示产品页、打分与导出，"
        "不代表完整的美国海运提单库。正式使用需导入授权数据。"
    )
    sample_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
