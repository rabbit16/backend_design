"""症状追问解析与流式过滤。"""

from __future__ import annotations

import asyncio

from src.app.prompts.registry import clear_prompt_registry, get_prompt_registry
from src.app.schemas.openai_chat import (
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionChunkDelta,
    ChatCompletionRequest,
    ChatMessage,
)
from src.app.services.qa_intake import (
    IntakeStreamFilter,
    build_turn_hint,
    iterate_intake_stream,
    parse_intake_reply,
    render_intake_prompts,
)


def test_parse_followup_marker() -> None:
    reply = parse_intake_reply("FOLLOWUP\n\n您头疼几天了？是胀痛还是刺痛？")
    assert reply.phase == "followup"
    assert reply.answer == "您头疼几天了？是胀痛还是刺痛？"
    assert reply.intake_complete is False


def test_parse_diagnosis_marker() -> None:
    reply = parse_intake_reply("DIAGNOSIS\n\n更像是着凉引起的头疼，先休息观察。这不是医生诊断。")
    assert reply.phase == "diagnosis"
    assert "着凉" in reply.answer
    assert reply.intake_complete is True


def test_parse_emergency_and_json() -> None:
    emergency = parse_intake_reply("EMERGENCY\n\n请立刻拨打120去急诊。")
    assert emergency.phase == "emergency"
    assert emergency.intake_complete is True

    as_json = parse_intake_reply('{"phase":"diagnosis","answer":"更像是感冒。"}')
    assert as_json.phase == "diagnosis"
    assert as_json.answer == "更像是感冒。"


def test_filter_strips_phase_and_streams_spoken() -> None:
    filt = IntakeStreamFilter()
    out: list[str] = []
    for piece in ["FOL", "LOWUP\n\n", "您头疼几天了？"]:
        spoken = filt.feed(piece)
        if spoken:
            out.append(spoken)
    reply = filt.finish()
    assert "".join(out) == "您头疼几天了？"
    assert reply.phase == "followup"
    assert reply.answer == "您头疼几天了？"
    assert reply.flushed_tokens == ""


def test_filter_echo_passthrough() -> None:
    filt = IntakeStreamFilter()
    out: list[str] = []
    for piece in ["echo", ": ", "今天天气怎么样"]:
        spoken = filt.feed(piece)
        if spoken:
            out.append(spoken)
    reply = filt.finish()
    assert "".join(out) == "echo: 今天天气怎么样"
    assert reply.answer == "echo: 今天天气怎么样"
    assert reply.phase == "followup"


def test_filter_json_flushes_on_finish() -> None:
    filt = IntakeStreamFilter()
    assert filt.feed('{"phase":"diagnosis","answer":"更像是感冒。"}') == ""
    reply = filt.finish()
    assert reply.phase == "diagnosis"
    assert reply.answer == "更像是感冒。"
    assert reply.flushed_tokens == "更像是感冒。"


def test_turn_hint_forces_diagnosis_at_cap() -> None:
    hint = build_turn_hint(6, 6)
    assert "必须 DIAGNOSIS" in hint
    early = build_turn_hint(1, 6)
    assert "第 1 轮" in early


def test_prompt_registry_has_intake_template() -> None:
    clear_prompt_registry()
    prompt = get_prompt_registry().get("qa_symptom_intake")
    system, user = render_intake_prompts(question="我头疼", user_turn=1, lang="zh")
    assert "追问" in prompt.system or "追问" in system
    assert "FOLLOWUP" in system
    assert user == "我头疼"
    assert "第 1 轮" in system


class _ScriptedGateway:
    provider = "scripted"

    def __init__(self, text: str) -> None:
        self.text = text
        self.last_request: ChatCompletionRequest | None = None

    async def chat_completions_stream(self, request: ChatCompletionRequest):
        self.last_request = request
        yield ChatCompletionChunk(
            choices=[
                ChatCompletionChunkChoice(
                    delta=ChatCompletionChunkDelta(role="assistant", content="")
                )
            ]
        )
        yield ChatCompletionChunk(
            choices=[
                ChatCompletionChunkChoice(delta=ChatCompletionChunkDelta(content=self.text))
            ]
        )
        yield ChatCompletionChunk(
            choices=[
                ChatCompletionChunkChoice(
                    delta=ChatCompletionChunkDelta(), finish_reason="stop"
                )
            ]
        )

    async def close(self) -> None:
        return None


def test_iterate_intake_stream_strips_marker() -> None:
    gateway = _ScriptedGateway("FOLLOWUP\n\n您哪里不舒服？")
    req = ChatCompletionRequest(model="x", messages=[ChatMessage(role="user", content="头疼")])

    async def _collect() -> list[dict]:
        events = []
        async for event in iterate_intake_stream(gateway, req, owns_gateway=False):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    types = [e["type"] for e in events]
    assert "phase" in types
    assert "token" in types
    assert types[-1] == "_complete"
    deltas = "".join(e["delta"] for e in events if e["type"] == "token")
    assert deltas == "您哪里不舒服？"
    assert events[-1]["reply"].phase == "followup"
    phase_events = [e for e in events if e["type"] == "phase"]
    assert phase_events[0]["phase"] == "followup"
