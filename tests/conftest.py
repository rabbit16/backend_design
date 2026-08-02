"""pytest 默认用内存 SQLite，避免依赖本机 MySQL。"""

from __future__ import annotations

import os

# 必须在导入 app.* 之前设置（pytest 会先加载 conftest）
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ.setdefault("SMS_DEV_CODE", "123456")
