"""可替换的 Prompt 模板：只替换 {{key}}，正文里的 JSON 花括号不会被误伤。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


def substitute(text: str, variables: dict[str, str]) -> str:
    rendered = text
    for key, value in variables.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return rendered


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str


class PromptTemplate(Protocol):
    name: str

    def render(self, **variables: str) -> RenderedPrompt:
        ...


class StringPromptTemplate:
    def __init__(self, name: str, system: str, user: str, *, description: str = "") -> None:
        self.name = name
        self.system = system
        self.user = user
        self.description = description

    def render(self, **variables: str) -> RenderedPrompt:
        mapping = {str(k): str(v) for k, v in variables.items()}
        return RenderedPrompt(
            system=substitute(self.system, mapping),
            user=substitute(self.user, mapping),
        )

    @classmethod
    def from_mapping(cls, payload: dict[str, object], *, fallback_name: str = "unnamed") -> StringPromptTemplate:
        name = str(payload.get("name") or fallback_name)
        system = str(payload.get("system") or "")
        user = str(payload.get("user") or "")
        if not system.strip() or not user.strip():
            raise ValueError(f"prompt {name!r} 需要非空 system 与 user")
        return cls(
            name=name,
            system=system,
            user=user,
            description=str(payload.get("description") or ""),
        )

    @classmethod
    def from_path(cls, path: Path) -> StringPromptTemplate:
        import json

        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"prompt 文件必须是 JSON 对象: {path}")
        return cls.from_mapping(raw, fallback_name=path.stem)

    @classmethod
    def from_bytes(cls, name: str, data: bytes) -> StringPromptTemplate:
        import json

        raw = json.loads(data.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"prompt 文件必须是 JSON 对象: {name}")
        return cls.from_mapping(raw, fallback_name=Path(name).stem)
