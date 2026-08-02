from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI FastAPI Backend"
    app_env: Literal["local", "dev", "test", "staging", "prod"] = "local"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    api_v1_prefix: str = "/api/v1"
    ws_v1_prefix: str = "/ws/v1"

    log_level: str = "INFO"
    access_log: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    ai_gateway_provider: str = "echo"
    ai_gateway_timeout_seconds: float = 60.0

    max_ws_connections: int = 10_000

    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 40

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = False
    redis_max_connections: int = 100

    rate_limit_enabled: bool = True
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120
    jwt_refresh_token_expire_days: int = 30

    sms_code_expire_seconds: int = 300
    sms_rate_limit_seconds: int = 60
    sms_code_length: int = 6
    # 本地/测试固定验证码；生产环境请置空并接入真实短信通道
    sms_dev_code: str = "123456"

    telemetry_enabled: bool = False
    telemetry_service_name: str = "ai-fastapi-backend"
    telemetry_otlp_endpoint: str | None = None

    task_worker_count: int = 2
    task_queue_max_size: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
