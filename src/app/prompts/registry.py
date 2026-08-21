from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.app.core.config import get_settings
from src.app.core.exceptions import AppError
from src.app.prompts.base import PromptTemplate, StringPromptTemplate
from src.app.prompts.defaults import BUILTIN_PROMPTS


class PromptRegistry:
    """按名称取 prompt；包内 JSON、外部目录、OCR_PROMPT_PATH 均可覆盖。"""

    def __init__(self) -> None:
        self._items: dict[str, PromptTemplate] = dict(BUILTIN_PROMPTS)

    def register(self, template: PromptTemplate) -> None:
        self._items[template.name] = template

    def get(self, name: str) -> PromptTemplate:
        template = self._items.get(name)
        if template is None:
            available = ", ".join(sorted(self._items)) or "(empty)"
            raise AppError(
                f"未找到 prompt: {name!r}，已加载: {available}",
                code="prompt_not_found",
                status_code=500,
            )
        return template

    def load_packaged(self) -> None:
        try:
            from importlib.resources import files
        except ImportError:  # pragma: no cover
            return
        try:
            root = files("src.app.prompts.templates")
        except ModuleNotFoundError:
            return
        for item in root.iterdir():
            if item.name.endswith(".json"):
                self.register(StringPromptTemplate.from_bytes(item.name, item.read_bytes()))

    def load_dir(self, directory: Path) -> None:
        if not directory.is_dir():
            return
        for path in sorted(directory.glob("*.json")):
            self.register(StringPromptTemplate.from_path(path))

    def load_file(self, path: Path) -> None:
        if not path.is_file():
            raise AppError(
                f"prompt 文件不存在: {path}",
                code="prompt_file_missing",
                status_code=500,
            )
        self.register(StringPromptTemplate.from_path(path))


def build_prompt_registry() -> PromptRegistry:
    settings = get_settings()
    registry = PromptRegistry()
    registry.load_packaged()
    if settings.ocr_prompt_dir.strip():
        registry.load_dir(Path(settings.ocr_prompt_dir))
    if settings.ocr_prompt_path.strip():
        registry.load_file(Path(settings.ocr_prompt_path))
    return registry


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    return build_prompt_registry()


def clear_prompt_registry() -> None:
    get_prompt_registry.cache_clear()
