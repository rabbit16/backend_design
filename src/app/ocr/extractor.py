"""用 OpenAI Chat Completions vision（image_url）识别就诊单或体检单。"""

from __future__ import annotations

from datetime import date

from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.core.logging import get_logger
from src.app.gateways.base import AIGateway
from src.app.ocr.image import sniff_image_mime, source_label, to_data_url, validate_image_bytes
from src.app.ocr.parser import ExtractedDocument, OcrResultParser, ocr_json_schema_text, openai_json_object_format
from src.app.prompts.base import PromptTemplate
from src.app.prompts.registry import get_prompt_registry
from src.app.schemas.openai_chat import (
    ChatCompletionRequest,
    ChatMessage,
    ImageDetail,
    ImageUrl,
    ImageUrlContentPart,
    TextContentPart,
)

logger = get_logger(__name__)


class VisionOcrExtractor:
    """面向对象的视觉 OCR：prompt 可替换，请求形状符合 OpenAI Chat Completions。"""

    def __init__(
        self,
        gateway: AIGateway,
        prompt: PromptTemplate | None = None,
        parser: OcrResultParser | None = None,
        *,
        model: str | None = None,
        image_detail: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_image_bytes: int | None = None,
    ) -> None:
        settings = get_settings()
        self.gateway = gateway
        self.prompt = prompt or get_prompt_registry().get(settings.ocr_prompt_name)
        self.parser = parser or OcrResultParser()
        self.model = model or settings.openai_vision_model.strip() or settings.openai_model
        self.image_detail = image_detail or settings.ocr_image_detail
        self.temperature = settings.ocr_temperature if temperature is None else temperature
        self.max_tokens = settings.ocr_max_tokens if max_tokens is None else max_tokens
        self.max_image_bytes = (
            settings.ocr_max_image_bytes if max_image_bytes is None else max_image_bytes
        )

    def build_request(
        self,
        image_bytes: bytes,
        *,
        mime_type: str,
        source: str,
        user_id: str | None = None,
    ) -> ChatCompletionRequest:
        rendered = self.prompt.render(
            today=date.today().isoformat(),
            source=source,
            source_label=source_label(source),
            json_schema=ocr_json_schema_text(),
        )
        detail: ImageDetail = (
            self.image_detail if self.image_detail in {"auto", "low", "high"} else "high"
        )
        return ChatCompletionRequest(
            model=self.model,
            messages=[
                ChatMessage(role="system", content=rendered.system),
                ChatMessage(
                    role="user",
                    content=[
                        TextContentPart(text=rendered.user),
                        ImageUrlContentPart(
                            image_url=ImageUrl(
                                url=to_data_url(image_bytes, mime_type),
                                detail=detail,
                            )
                        ),
                    ],
                ),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format=openai_json_object_format(),
            user=user_id,
        )

    async def extract(
        self,
        image_bytes: bytes,
        *,
        source: str,
        filename: str | None = None,
        content_type: str | None = None,
        user_id: str | None = None,
    ) -> ExtractedDocument:
        validate_image_bytes(image_bytes, max_bytes=self.max_image_bytes)
        mime_type = sniff_image_mime(image_bytes, filename=filename, content_type=content_type)
        request = self.build_request(
            image_bytes,
            mime_type=mime_type,
            source=source,
            user_id=user_id,
        )
        logger.info(
            "ocr_vision_request",
            model=request.model,
            mime_type=mime_type,
            image_bytes=len(image_bytes),
            prompt=getattr(self.prompt, "name", "unknown"),
            source=source,
        )
        completion = await self.gateway.chat_completions(request)
        content = completion.content
        if not content.strip():
            raise AppError("模型未返回识别结果", code="ocr_empty_response", status_code=502)
        result = self.parser.parse(content)
        logger.info(
            "ocr_vision_response",
            model=completion.model,
            document_type=result.document_type,
            visit_no=result.visit_no,
            content_len=len(content),
        )
        return result
