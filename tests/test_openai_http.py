"""验证 OpenAICompatibleGateway 会真正 POST /chat/completions。"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.gateways.openai_compatible import OpenAICompatibleGateway
from app.schemas.openai_chat import ChatCompletionRequest, ChatMessage


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
