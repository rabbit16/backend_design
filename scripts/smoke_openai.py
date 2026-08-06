#!/usr/bin/env python3
"""冒烟：直接打一次 OpenAI 兼容 /chat/completions（读 .env）。"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import clear_settings_cache, get_settings
from app.gateways.openai_compatible import OpenAICompatibleGateway
from app.schemas.openai_chat import ChatCompletionRequest, ChatMessage


async def main() -> int:
    clear_settings_cache()
    settings = get_settings()
    print(f"provider={settings.ai_gateway_provider}")
    print(f"api_base={settings.openai_api_base}")
    print(f"model={settings.openai_model}")
    print(f"has_api_key={bool(settings.openai_api_key.strip())}")

    if settings.ai_gateway_provider.strip().lower() != "openai":
        print("AI_GATEWAY_PROVIDER 不是 openai，跳过真实请求", file=sys.stderr)
        return 2
    if not settings.openai_api_key.strip():
        print("OPENAI_API_KEY 为空，请写入 .env 后再试", file=sys.stderr)
        return 2

    gw = OpenAICompatibleGateway()
    try:
        resp = await gw.chat_completions(
            ChatCompletionRequest(
                model=settings.openai_model,
                messages=[
                    ChatMessage(role="system", content="用一句话中文回答。"),
                    ChatMessage(role="user", content="1+1等于几？"),
                ],
                temperature=0,
                max_tokens=64,
            )
        )
        print(f"id={resp.id}")
        print(f"model={resp.model}")
        print(f"content={resp.content!r}")
        return 0
    finally:
        await gw.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
