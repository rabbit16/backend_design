"""OpenAI 协议与网关单测。"""

import pytest

from src.app.gateways.ai_gateway import EchoAIGateway
from src.app.schemas.chat import ChatRequest
from src.app.schemas.openai_chat import ChatCompletionRequest, ChatMessage


@pytest.mark.asyncio
async def test_echo_openai_chat_completions() -> None:
    gw = EchoAIGateway()
    req = ChatCompletionRequest(
        model="echo",
        messages=[
            ChatMessage(role="system", content="你是助手"),
            ChatMessage(role="user", content="你好"),
        ],
    )
    resp = await gw.chat_completions(req)
    assert resp.object == "chat.completion"
    assert resp.content == "echo: 你好"
    assert resp.provider == "echo"
    await gw.close()


@pytest.mark.asyncio
async def test_echo_openai_stream_chunks() -> None:
    gw = EchoAIGateway()
    req = ChatCompletionRequest(
        model="echo",
        messages=[ChatMessage(role="user", content="流式")],
        stream=True,
    )
    parts: list[str] = []
    async for chunk in gw.chat_completions_stream(req):
        assert chunk.object == "chat.completion.chunk"
        if chunk.delta_content:
            parts.append(chunk.delta_content)
    assert "".join(parts) == "echo: 流式"
    await gw.close()


def test_chat_request_to_openai_messages() -> None:
    req = ChatRequest(message="hello", system_prompt="sys", model="echo")
    openai_req = req.to_openai()
    assert openai_req.messages[0].role == "system"
    assert openai_req.messages[1].role == "user"
    assert openai_req.messages[1].content == "hello"
