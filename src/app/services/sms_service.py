from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass
from typing import Literal

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

SmsPurpose = Literal["login", "register", "reset_password"]
VALID_PURPOSES = {"login", "register", "reset_password"}


@dataclass
class SmsCodeRecord:
    code: str
    purpose: str
    expires_at: float
    last_sent_at: float


_sms_store: dict[str, SmsCodeRecord] = {}


def clear_sms_store() -> None:
    _sms_store.clear()


def _store_key(phone: str, purpose: str) -> str:
    return f"{phone}:{purpose}"


class SmsService:
    """开发期内存短信验证码；生产可替换为真实短信网关。"""

    def send_code(self, phone: str, purpose: SmsPurpose = "login") -> int:
        if purpose not in VALID_PURPOSES:
            raise AppError("无效的验证码用途", code="invalid_sms_purpose", status_code=400)

        settings = get_settings()
        now = time.monotonic()
        key = _store_key(phone, purpose)
        existing = _sms_store.get(key)
        if existing and now - existing.last_sent_at < settings.sms_rate_limit_seconds:
            raise AppError(
                "验证码发送过于频繁，请稍后再试",
                code="sms_rate_limited",
                status_code=429,
            )

        if settings.app_env in {"local", "dev", "test"} and settings.sms_dev_code:
            code = settings.sms_dev_code
        else:
            length = settings.sms_code_length
            code = "".join(random.choices(string.digits, k=length))

        _sms_store[key] = SmsCodeRecord(
            code=code,
            purpose=purpose,
            expires_at=now + settings.sms_code_expire_seconds,
            last_sent_at=now,
        )
        logger.info(
            "sms_code_sent",
            phone=phone,
            purpose=purpose,
            expire_in=settings.sms_code_expire_seconds,
        )
        if settings.app_env in {"local", "dev", "test"}:
            logger.info("sms_dev_code", phone=phone, purpose=purpose, code=code)
        return settings.sms_code_expire_seconds

    def verify_code(
        self,
        phone: str,
        code: str,
        purpose: SmsPurpose = "login",
        *,
        status_code: int = 400,
    ) -> None:
        key = _store_key(phone, purpose)
        record = _sms_store.get(key)
        if (
            record is None
            or record.purpose != purpose
            or time.monotonic() > record.expires_at
            or record.code != code
        ):
            raise AppError(
                "验证码错误或已过期",
                code="invalid_sms_code",
                status_code=status_code,
            )
        _sms_store.pop(key, None)
