"""验证 OpenAICompatibleGateway 会真正 POST /chat/completions。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from src.app.gateways.openai_compatible import OpenAICompatibleGateway
from src.app.schemas.openai_chat import (
    ChatCompletionRequest,
    ChatMessage,
    ImageUrl,
    ImageUrlContentPart,
    TextContentPart,
)


@pytest.mark.asyncio
@respx.mock
async def test_openai_gateway_posts_chat_completions() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "真实模型回答"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )
    )

    gw = OpenAICompatibleGateway(
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        default_model="gpt-4o-mini",
        trust_env=False,
    )
    try:
        resp = await gw.chat_completions(
            ChatCompletionRequest(
                model="gpt-4o-mini",
                messages=[ChatMessage(role="user", content="你好")],
            )
        )
    finally:
        await gw.close()

    assert route.called
    sent = json.loads(route.calls.last.request.content.decode())
    assert sent["model"] == "gpt-4o-mini"
    assert sent["messages"][0]["content"] == "你好"
    assert sent["stream"] is False
    assert resp.content == "真实模型回答"
    assert resp.provider == "openai"


@pytest.mark.asyncio
@respx.mock
async def test_openai_gateway_stream_posts() -> None:
    sse = (
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"gpt-4o-mini",'
        '"choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n'
        'data: {"id":"c1","object":"chat.completion.chunk","created":1,"model":"gpt-4o-mini",'
        '"choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}\n\n'
        "data: [DONE]\n\n"
    )
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    )

    gw = OpenAICompatibleGateway(
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        default_model="gpt-4o-mini",
        trust_env=False,
    )
    parts: list[str] = []
    try:
        async for chunk in gw.chat_completions_stream(
            ChatCompletionRequest(
                model="gpt-4o-mini",
                messages=[ChatMessage(role="user", content="hi")],
                stream=True,
            )
        ):
            if chunk.delta_content:
                parts.append(chunk.delta_content)
    finally:
        await gw.close()

    assert route.called
    sent = json.loads(route.calls.last.request.content.decode())
    assert sent["stream"] is True
    assert "".join(parts) == "你好"


@pytest.mark.asyncio
@respx.mock
async def test_openai_gateway_posts_vision_image_url() -> None:
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "chatcmpl-vision",
                "object": "chat.completion",
                "created": 1,
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "diagnosis": "感冒",
                                    "medicine": "感冒灵",
                                    "visit_date": "2026-07-27",
                                    "visit_no": "MZ1",
                                    "raw_ocr_text": "全文",
                                },
                                ensure_ascii=False,
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
            },
        )
    )
    gw = OpenAICompatibleGateway(
        api_base="https://api.openai.com/v1",
        api_key="sk-test",
        default_model="gpt-4o-mini",
        trust_env=False,
    )
    try:
        resp = await gw.chat_completions(
            ChatCompletionRequest(
                model="gpt-4o-mini",
                messages=[
                    ChatMessage(role="system", content="ocr"),
                    ChatMessage(
                        role="user",
                        content=[
                            TextContentPart(text="识别就诊单"),
                            ImageUrlContentPart(
                                image_url=ImageUrl(
                                    url="data:image/jpeg;base64,AAAA",
                                    detail="high",
                                )
                            ),
                        ],
                    ),
                ],
                response_format={"type": "json_object"},
            )
        )
    finally:
        await gw.close()

    assert route.called
    sent = json.loads(route.calls.last.request.content.decode())
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["messages"][1]["content"][1]["type"] == "image_url"
    assert sent["messages"][1]["content"][1]["image_url"]["detail"] == "high"
    assert "感冒" in resp.content
