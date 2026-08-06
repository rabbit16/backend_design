from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str
    message: str


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    env: str
    ai_provider: str | None = None
    openai_model: str | None = None
    openai_configured: bool | None = None


class PageParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
