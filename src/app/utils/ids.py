from uuid import uuid4


def new_request_id() -> str:
    return uuid4().hex


def new_uuid() -> str:
    """生成符合 MySQL CHAR(36) 主键的标准 UUID 字符串。"""
    return str(uuid4())


def new_user_id() -> str:
    return new_uuid()
