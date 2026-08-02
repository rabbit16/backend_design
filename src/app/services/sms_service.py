from __future__ import annotations

import random
import string
import time
from dataclasses import dataclass

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SmsCodeRecord:
    code: str
    expires_at: float
    last_sent_at: float


_sms_store: dict[str, SmsCodeRecord] = {}


def clear_sms_store() -> None:
    _sms_store.clear()


class SmsService:
    """开发期内存短信验证码；生产可替换为真实短信网关。"""

    def send_code(self, phone: str) -> int:
        settings = get_settings()
        now = time.monotonic()
        existing = _sms_store.get(phone)
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

        _sms_store[phone] = SmsCodeRecord(
            code=code,
            expires_at=now + settings.sms_code_expire_seconds,
            last_sent_at=now,
        )
        logger.info("sms_code_sent", phone=phone, expire_in=settings.sms_code_expire_seconds)
        if settings.app_env in {"local", "dev", "test"}:
            logger.info("sms_dev_code", phone=phone, code=code)
        return settings.sms_code_expire_seconds

    def verify_code(self, phone: str, code: str) -> None:
        record = _sms_store.get(phone)
        if record is None or time.monotonic() > record.expires_at or record.code != code:
            raise AppError(
                "验证码错误或已过期",
                code="invalid_sms_code",
                status_code=400,
            )
        # 验证成功后消费验证码，防止重复使用
        _sms_store.pop(phone, None)
