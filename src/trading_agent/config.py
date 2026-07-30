from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_AGENT_")

    environment: str = "test"
    enable_order_execution: bool = False
    primary_vision_provider: str = "codex"
    codex_model: str = "gpt-5.6-sol"
    codex_model_provider: str | None = None
    codex_provider_base_url: str | None = None
    codex_provider_env_key: str | None = None
    kimi_model: str = "kimi-k3"
    market_data_provider: Literal["none", "free", "http"] = "none"
    market_data_history_length: int = 240
    market_data_timeout_seconds: float = 10.0
    market_data_validate_exchange_daily: bool = True
    tqsdk_username: str | None = None
    tqsdk_password: str | None = None
