"""pytest 默认用内存 SQLite + echo 网关，避免依赖本机 MySQL / 真实 LLM。"""

from __future__ import annotations

import os

# 必须在导入 app.* 之前设置（pytest 会先加载 conftest）
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["AI_GATEWAY_PROVIDER"] = "echo"
os.environ["OPENAI_API_KEY"] = ""
os.environ["REDIS_ENABLED"] = "false"
os.environ.setdefault("SMS_DEV_CODE", "123456")

from app.core.config import clear_settings_cache

clear_settings_cache()
