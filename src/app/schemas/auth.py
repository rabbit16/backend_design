from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["zh", "en"]


class SendSmsRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=20)


class SendSmsResponse(BaseModel):
    ok: bool = True
    expire_in: int


class SmsLoginRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    code: str = Field(min_length=1, max_length=16)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class PasswordLoginRequest(BaseModel):
    phone: str = Field(min_length=1, max_length=20)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str | None = Field(default=None, max_length=128)
    new_password: str = Field(min_length=6, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class OkResponse(BaseModel):
    ok: bool = True


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserProfile(BaseModel):
    id: str
    phone: str
    display_name: str | None = None
    preferred_lang: Lang = "zh"
    created_at: str


class LoginResponse(TokenPair):
    user: UserProfile


# 兼容旧脚手架测试/文档中的简易发 token 接口
class TokenRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
