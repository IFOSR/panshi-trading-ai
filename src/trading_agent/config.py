from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TRADING_AGENT_")

    environment: str = "test"
    enable_order_execution: bool = False
    primary_vision_provider: str = "codex"
    fallback_vision_provider: str = "kimi"
    codex_model: str = "gpt-5.6-sol"
