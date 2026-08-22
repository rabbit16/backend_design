"""首页问询：症状追问 → 信息足够后给出初步判断。"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.db.models.qa import QaMessage
from src.app.gateways.base import AIGateway
from src.app.prompts.registry import get_prompt_registry
from src.app.schemas.openai_chat import ChatCompletionRequest, ChatMessage

QaPhase = Literal["followup", "diagnosis", "emergency"]

PHASE_LABELS: dict[str, QaPhase] = {
    "FOLLOWUP": "followup",
    "DIAGNOSIS": "diagnosis",
    "EMERGENCY": "emergency",
    "追问": "followup",
    "诊断": "diagnosis",
    "急救": "emergency",
}

_PHASE_MARKERS = ("FOLLOWUP", "DIAGNOSIS", "EMERGENCY", "PHASE", "追问", "诊断", "急救")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_QUESTION_HINTS = ("？", "?", "吗", "呢？", "请您", "能不能告诉", "方便说一下")
_EMERGENCY_HINTS = ("拨打120", "打120", "去急诊", "马上就医", "立刻就医", "急救")
_DIAGNOSIS_HINTS = ("初步", "可能是", "更像是", "看起来像", "建议您", "先观察")


@dataclass(frozen=True)
class IntakeReply:
    phase: QaPhase
    answer: str
    flushed_tokens: str = ""

    @property
    def intake_complete(self) -> bool:
        return self.phase in {"diagnosis", "emergency"}


def count_user_turns(history: list[QaMessage]) -> int:
    return sum(1 for msg in history if msg.role == "user")


def lang_instruction(lang: str) -> str:
    if lang == "en":
        return "Please reply in short, plain spoken English."
    return "请始终用简短、清楚、口语化的中文。"


def build_turn_hint(user_turn: int, max_turns: int) -> str:
    if user_turn >= max_turns:
        return (
            f"当前已是第 {user_turn} 轮（上限 {max_turns} 轮）。"
            "本轮必须 DIAGNOSIS 或 EMERGENCY，禁止再追问。"
        )
    remaining = max_turns - user_turn
    return (
        f"当前是第 {user_turn} 轮用户陈述，最多还可追问 {remaining} 轮。"
        "关键信息已经够了就 DIAGNOSIS，不要为了问而问。"
    )


def render_intake_prompts(
    *,
    question: str,
    user_turn: int,
    lang: str = "zh",
) -> tuple[str, str]:
    settings = get_settings()
    template = get_prompt_registry().get(settings.qa_prompt_name)
    rendered = template.render(
        question=question,
        turn_hint=build_turn_hint(user_turn, settings.qa_max_followup_turns),
        lang_instruction=lang_instruction(lang),
    )
    return rendered.system, rendered.user


def normalize_phase_line(line: str) -> QaPhase | None:
    text = _FENCE_RE.sub("", line.strip()).strip().strip("`").strip()
    if not text:
        return None
    if text.lower().startswith("phase"):
        _, _, rest = text.partition(":")
        if not rest.strip() and "：" in text:
            rest = text.split("：", 1)[1]
        text = rest.strip() or text
    key = text.upper()
    if key in PHASE_LABELS:
        return PHASE_LABELS[key]
    lower = text.lower()
    if lower in {"followup", "diagnosis", "emergency"}:
        return lower  # type: ignore[return-value]
    if text in PHASE_LABELS:
        return PHASE_LABELS[text]
    return None


def infer_phase(answer: str) -> QaPhase:
    text = answer.strip()
    if any(hint in text for hint in _EMERGENCY_HINTS):
        return "emergency"
    if any(hint in text for hint in _DIAGNOSIS_HINTS):
        return "diagnosis"
    if any(hint in text for hint in _QUESTION_HINTS):
        return "followup"
    return "followup"


def parse_intake_json(raw: str) -> IntakeReply | None:
    stripped = _FENCE_RE.sub("", raw.strip()).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    phase_raw = str(data.get("phase") or data.get("type") or "")
    phase = normalize_phase_line(phase_raw) or infer_phase(str(data.get("answer") or ""))
    answer = str(data.get("answer") or data.get("text") or data.get("content") or "").strip()
    if not answer:
        return None
    return IntakeReply(phase=phase, answer=answer, flushed_tokens=answer)


def parse_intake_reply(raw: str) -> IntakeReply:
    text = raw.strip()
    if not text:
        return IntakeReply(phase="followup", answer="")

    json_reply = parse_intake_json(text)
    if json_reply is not None:
        return json_reply

    lines = text.splitlines()
    phase: QaPhase | None = None
    start = 0
    for idx, line in enumerate(lines):
        if not line.strip() or line.strip().startswith("```"):
            continue
        parsed = normalize_phase_line(line)
        if parsed is not None:
            phase = parsed
            start = idx + 1
            break
        break
    if phase is not None:
        while start < len(lines) and not lines[start].strip():
            start += 1
        answer = "\n".join(lines[start:]).strip()
        return IntakeReply(phase=phase, answer=answer, flushed_tokens=answer)

    answer = text
    return IntakeReply(phase=infer_phase(answer), answer=answer, flushed_tokens="")


def _is_marker_prefix(buffer: str) -> bool:
    stripped = buffer.lstrip()
    if not stripped:
        return True
    if stripped.startswith("{"):
        return True
    upper = stripped.upper()
    for marker in _PHASE_MARKERS:
        if marker.startswith(upper) or marker.startswith(stripped):
            return True
        if upper.startswith(marker) or stripped.startswith(marker):
            return True
    return False


class IntakeStreamFilter:
    """流式去掉 PHASE 行 / JSON 外壳，只把对老人说的话当作 token。"""

    def __init__(self) -> None:
        self._buf = ""
        self._unlocked = False
        self._json_mode = False
        self._phase: QaPhase | None = None
        self._spoken: list[str] = []
        self._phase_emitted = False

    @property
    def phase(self) -> QaPhase | None:
        return self._phase

    @property
    def phase_emitted(self) -> bool:
        return self._phase_emitted

    def pop_phase_event(self) -> QaPhase | None:
        if self._phase is None or self._phase_emitted:
            return None
        self._phase_emitted = True
        return self._phase

    def feed(self, delta: str) -> str:
        if not delta:
            return ""
        if self._unlocked:
            self._spoken.append(delta)
            return delta

        self._buf += delta
        stripped = self._buf.lstrip()
        if stripped.startswith("{") or self._json_mode:
            self._json_mode = True
            return ""

        if "\n" in self._buf:
            first, rest = self._buf.split("\n", 1)
            phase = normalize_phase_line(first)
            if phase is not None:
                self._phase = phase
                rest = rest.lstrip("\n")
                self._unlocked = True
                self._buf = ""
                if rest:
                    self._spoken.append(rest)
                return rest
            # 首行不是阶段标记：整段当口语
            self._unlocked = True
            spoken = self._buf
            self._buf = ""
            self._spoken.append(spoken)
            return spoken

        if not _is_marker_prefix(self._buf):
            self._unlocked = True
            spoken = self._buf
            self._buf = ""
            self._spoken.append(spoken)
            return spoken
        return ""

    def finish(self) -> IntakeReply:
        if self._json_mode or self._buf.lstrip().startswith("{"):
            parsed = parse_intake_reply(self._buf)
            return IntakeReply(
                phase=parsed.phase,
                answer=parsed.answer,
                flushed_tokens=parsed.answer,
            )

        if not self._unlocked:
            parsed = parse_intake_reply(self._buf)
            return IntakeReply(
                phase=parsed.phase,
                answer=parsed.answer,
                flushed_tokens=parsed.answer,
            )

        leftover = self._buf
        answer = ("".join(self._spoken) + leftover).strip()
        return IntakeReply(
            phase=self._phase or infer_phase(answer),
            answer=answer,
            flushed_tokens=leftover,
        )


async def iterate_intake_stream(
    gateway: AIGateway,
    request: ChatCompletionRequest,
    *,
    owns_gateway: bool,
) -> AsyncIterator[dict[str, Any]]:
    """把模型流整理成 token / phase / error，最后一条 type=_complete。"""
    filt = IntakeStreamFilter()
    try:
        async for chunk in gateway.chat_completions_stream(request):
            delta = chunk.delta_content
            if not delta:
                continue
            spoken = filt.feed(delta)
            phase_event = filt.pop_phase_event()
            if phase_event is not None:
                yield {"type": "phase", "phase": phase_event}
            if spoken:
                yield {"type": "token", "delta": spoken}
    except AppError as exc:
        yield {"type": "error", "code": exc.code, "message": exc.message}
        return
    except Exception as exc:  # noqa: BLE001
        yield {
            "type": "error",
            "code": "qa_stream_failed",
            "message": str(exc) or "生成回答失败",
        }
        return
    finally:
        if owns_gateway:
            await gateway.close()

    reply = filt.finish()
    if not filt.phase_emitted:
        yield {"type": "phase", "phase": reply.phase}
    if reply.flushed_tokens:
        yield {"type": "token", "delta": reply.flushed_tokens}
    yield {"type": "_complete", "reply": reply}


def history_chat_messages(
    history: list[QaMessage],
    system_prompt: str,
) -> list[ChatMessage]:
    settings = get_settings()
    recent = history[-settings.qa_context_history_limit :]
    messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]
    for msg in recent:
        if msg.role == "user":
            messages.append(ChatMessage(role="user", content=msg.content))
        elif msg.role == "assistant":
            messages.append(ChatMessage(role="assistant", content=msg.content))
    return messages
