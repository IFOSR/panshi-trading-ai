from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_AGENT_")

    environment: str = "test"
    enable_order_execution: bool = False
    primary_vision_provider: str = "deepseek"
    fallback_vision_provider: str = "kimi"
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_env_key: str = "DEEPSEEK_API_KEY"
    kimi_model: str = "default"
    kimi_external_isolation_verified: bool = False
    kimi_isolation_provider: str | None = None
    market_data_provider: Literal["none", "free", "http"] = "none"
    market_data_history_length: int = 240
    market_data_timeout_seconds: float = 10.0
    market_data_validate_exchange_daily: bool = True
    tqsdk_username: str | None = None
    tqsdk_password: str | None = None
