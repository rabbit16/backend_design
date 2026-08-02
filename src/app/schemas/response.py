from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str = "ok"
    message: str = "success"
    data: T | None = None


def ok(data: T | None = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse(data=data, message=message)
