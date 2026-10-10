"""应用配置：环境变量 + .env（pydantic-settings），凭据不进源码。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRUEORDER_", env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://trueorder:trueorder@localhost:5433/trueorder"
    )
    # CSV 上传上限（MB）：产品与提单导入端点共用，超出返回 413
    max_upload_mb: int = 20
    # WP4 补全：Hunter API Key（空 = 走 fake 演示数据并在界面提示）
    hunter_api_key: str = ""
    # 按次补全每日调用上限（合规约束：禁止无人触发的全库自动补全）
    enrich_daily_cap: int = 20
    # 样本声明：界面必须展示「非全量库」
    sample_notice: str = (
        "当前库内为公开样本数据（非全量样本）：仅用于演示产品页、打分与导出，"
        "不代表完整的美国海运提单库。正式使用需导入授权数据。"
    )
    sample_mode: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
