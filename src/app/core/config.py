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

    # echo | reverse-echo | openai（OpenAI 兼容 /chat/completions）
    ai_gateway_provider: str = "openai"
    ai_gateway_timeout_seconds: float = 120.0
    # OpenAI 兼容接口（DeepSeek / 通义 / vLLM / Ollama 等改 api_base 即可）
    openai_api_base: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    # 语音输入 → 文本输出（OpenAI audio chat 模型）
    openai_audio_model: str = "gpt-audio"
    # 视觉 OCR；空则回退 openai_model（需支持 image_url，如 gpt-4o-mini）
    openai_vision_model: str = ""
    openai_temperature: float = 0.7
    openai_max_tokens: int = 1024
    # 档案 OCR：prompt 名对应 app/prompts/templates/{name}.json，可被路径覆盖
    ocr_prompt_name: str = "archive_ocr"
    ocr_prompt_path: str = ""
    ocr_prompt_dir: str = ""
    ocr_max_image_bytes: int = 10 * 1024 * 1024
    ocr_image_detail: Literal["auto", "low", "high"] = "high"
    ocr_temperature: float = 0.0
    ocr_max_tokens: int = 4096
    # 可选：显式 HTTP 代理，如 http://127.0.0.1:7890；空则跟随环境变量
    openai_http_proxy: str = ""

    max_ws_connections: int = 10_000

    database_url: str = "mysql+aiomysql://root:123456@127.0.0.1:3306/senior_voice?charset=utf8mb4"
    database_echo: bool = False
    database_pool_size: int = 20
    database_max_overflow: int = 40

    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    redis_max_connections: int = 100

    # 适老化问答：服务端托管上下文；创建时固定 30 天过期，期内提问不续期
    qa_context_ttl_seconds: int = 30 * 24 * 60 * 60
    qa_context_history_limit: int = 40
    # 首页问询：症状追问轮次上限（含首轮）；达到后强制给出初步判断
    qa_max_followup_turns: int = 6
    qa_prompt_name: str = "qa_symptom_intake"

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


def clear_settings_cache() -> None:
    get_settings.cache_clear()
