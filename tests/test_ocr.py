from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from src.app.core.exceptions import AppError
from src.app.gateways.ai_gateway import EchoAIGateway
from src.app.ocr.extractor import VisionOcrExtractor
from src.app.ocr.image import sniff_image_mime, to_data_url
from src.app.ocr.parser import OcrResultParser, parse_visit_date
from src.app.prompts.base import StringPromptTemplate, substitute
from src.app.prompts.registry import PromptRegistry, clear_prompt_registry, get_prompt_registry
from src.app.schemas.openai_chat import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    ImageUrlContentPart,
    TextContentPart,
)


class RecordingGateway:
    provider = "recording"

    def __init__(self, content: str) -> None:
        self.content = content
        self.last_request: ChatCompletionRequest | None = None

    async def chat_completions(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        self.last_request = request
        return ChatCompletionResponse(
            id="chatcmpl-ocr",
            created=1,
            model=request.model or "gpt-4o-mini",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatMessage(role="assistant", content=self.content),
                    finish_reason="stop",
                )
            ],
            provider=self.provider,
        )

    async def chat_completions_stream(self, request: ChatCompletionRequest):
        if False:  # pragma: no cover
            yield request
        return

    async def close(self) -> None:
        return None


def test_prompt_only_replaces_mustache_keys() -> None:
    text = 'schema={"a":1} today={{today}}'
    assert substitute(text, {"today": "2026-08-18"}) == 'schema={"a":1} today=2026-08-18'


def test_archive_ocr_prompt_is_replaceable(tmp_path: Path) -> None:
    path = tmp_path / "custom_ocr.json"
    path.write_text(
        json.dumps(
            {
                "name": "archive_ocr",
                "system": "自定义系统 prompt",
                "user": "来源={{source}} 日期={{today}}",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    registry = PromptRegistry()
    registry.load_file(path)
    rendered = registry.get("archive_ocr").render(source="camera", today="2026-08-18")
    assert rendered.system == "自定义系统 prompt"
    assert "来源=camera" in rendered.user
    assert "日期=2026-08-18" in rendered.user


def test_packaged_archive_ocr_prompt_loads() -> None:
    clear_prompt_registry()
    prompt = get_prompt_registry().get("archive_ocr")
    rendered = prompt.render(
        today="2026-08-18",
        source="album",
        source_label="相册选择",
        json_schema='{"type":"object"}',
    )
    assert "严禁编造" in rendered.system
    assert "就医指引" in rendered.user
    assert "相册选择" in rendered.user
    assert "{{today}}" not in rendered.user


def test_parser_accepts_fenced_json_and_chinese_date() -> None:
    content = """```json
    {
      "diagnosis": "感冒",
      "medicine": "感冒灵",
      "visit_date": "2026年7月27日",
      "visit_no": "MZ1",
      "raw_ocr_text": "全文"
    }
    ```"""
    result = OcrResultParser().parse(content)
    assert result.document_type == "visit"
    assert result.diagnosis == "感冒"
    assert result.medicine == "感冒灵"
    assert result.visit_date == date(2026, 7, 27)
    assert result.visit_no == "MZ1"
    assert result.raw_ocr_text == "全文"


def test_parser_fills_missing_fields() -> None:
    result = OcrResultParser().parse('{"diagnosis":"","medicine":"","visit_date":"","visit_no":""}')
    assert result.document_type == "visit"
    assert result.diagnosis == "未能识别诊断"
    assert result.medicine == "未见用药信息"
    assert result.visit_date == date.today()
    assert result.visit_no.startswith("未编号-")
    assert result.raw_ocr_text


def test_parser_drops_hallucinated_visit_no_and_salvages_medicine() -> None:
    raw = (
        "首都医科大学附属北京天坛医院 就医指引单\n"
        "看诊科室 眼科门诊\n"
        "药品 [门诊药房取药]\n"
        "1: 氯化钠注射液*10ml:0.09g\n"
        "外用 每日一次 每次10ml 1支\n"
        "2: 普拉洛芬滴眼液@5mg 5ml\n"
        "滴眼 每日四次 每次1滴 1支\n"
        "检验 尿常规\n"
        "第 1 页/共 4 页"
    )
    payload = {
        "document_type": "exam",
        "diagnosis": "",
        "medicine": "未见用药信息",
        "visit_date": "",
        "visit_no": "MZ202407210018",
        "raw_ocr_text": raw,
    }
    result = OcrResultParser().parse(json.dumps(payload, ensure_ascii=False))
    assert result.document_type == "visit"
    assert result.visit_no.startswith("未编号-")
    assert "MZ202407210018" not in result.visit_no
    assert "氯化钠注射液" in result.medicine
    assert "普拉洛芬" in result.medicine


def test_parser_exam_document() -> None:
    content = """{
      "document_type": "exam",
      "patient_name": "毕小雪",
      "exam_date": "2025-11-03",
      "org_name": "瑞慈体检",
      "voucher_no": "312101033225",
      "findings": [
        {"title": "体重过低", "suggestion": "加强营养", "risk_level": "medium"}
      ],
      "raw_ocr_text": "体检全文"
    }"""
    result = OcrResultParser().parse(content)
    assert result.document_type == "exam"
    assert result.patient_name == "毕小雪"
    assert result.exam_date == date(2025, 11, 3)
    assert result.voucher_no == "312101033225"
    assert result.findings[0].title == "体重过低"
    ocr = result.to_ocr_result("hr_1")
    assert ocr.document_type == "exam"
    assert ocr.id == "hr_1"
    assert ocr.visit_no == "312101033225"
    assert ocr.visit_date == date(2025, 11, 3)


def test_parse_visit_date_formats() -> None:
    assert parse_visit_date("2026-07-27") == date(2026, 7, 27)
    assert parse_visit_date("2026/07/27") == date(2026, 7, 27)
    assert parse_visit_date("2026年07月27日") == date(2026, 7, 27)
    assert parse_visit_date("") is None


def test_parser_rejects_non_json() -> None:
    with pytest.raises(AppError) as exc:
        OcrResultParser().parse("not json")
    assert exc.value.code == "ocr_invalid_json"


@pytest.mark.asyncio
async def test_vision_extractor_builds_openai_image_url_request() -> None:
    payload = {
        "diagnosis": "支气管炎",
        "medicine": "止咳药",
        "visit_date": "2026-07-27",
        "visit_no": "MZ202607270018",
        "raw_ocr_text": "原始全文",
    }
    gateway = RecordingGateway(json.dumps(payload, ensure_ascii=False))
    prompt = StringPromptTemplate(
        name="archive_ocr",
        system="sys {{today}}",
        user="user {{source}} {{json_schema}}",
    )
    extractor = VisionOcrExtractor(gateway, prompt=prompt, model="gpt-4o-mini", image_detail="high")
    jpeg = b"\xff\xd8\xff" + b"fake-jpeg"
    result = await extractor.extract(
        jpeg,
        source="camera",
        filename="slip.jpg",
        content_type="image/jpeg",
        user_id="usr_1",
    )
    assert result.diagnosis == "支气管炎"
    assert result.visit_no == "MZ202607270018"
    assert result.document_type == "visit"
    req = gateway.last_request
    assert req is not None
    assert req.model == "gpt-4o-mini"
    assert req.response_format == {"type": "json_object"}
    assert req.messages[0].role == "system"
    user = req.messages[1]
    assert user.role == "user"
    assert isinstance(user.content, list)
    assert isinstance(user.content[0], TextContentPart)
    assert isinstance(user.content[1], ImageUrlContentPart)
    image = user.content[1].image_url
    assert image.detail == "high"
    assert image.url == to_data_url(jpeg, "image/jpeg")
    dumped = user.to_openai_param()
    assert dumped["content"][1]["type"] == "image_url"
    assert dumped["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_echo_gateway_returns_ocr_json_for_image() -> None:
    gw = EchoAIGateway()
    jpeg = b"\xff\xd8\xff" + b"x"
    extractor = VisionOcrExtractor(gw, model="echo")
    result = await extractor.extract(jpeg, source="album", filename="a.jpg", content_type="image/jpeg")
    await gw.close()
    assert result.document_type == "visit"
    assert result.diagnosis
    assert result.medicine
    assert result.visit_date
    assert result.visit_no
    assert result.raw_ocr_text


def test_sniff_jpeg_magic() -> None:
    assert sniff_image_mime(b"\xff\xd8\xffabc") == "image/jpeg"
    assert sniff_image_mime(b"not-an-image", content_type="image/png") == "image/png"
