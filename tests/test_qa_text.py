import json

from fastapi.testclient import TestClient

from src.app.main import create_app
from src.app.security.jwt import clear_revoked_sessions
from src.app.services.context_store import _memory_store, clear_context_store
from src.app.services.sms_service import clear_sms_store


def _auth_headers(client: TestClient, phone: str = "13100131000") -> dict[str, str]:
    client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "register"})
    reg = client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "code": "123456", "password": "secret12"},
    )
    if reg.status_code == 409:
        client.post("/api/v1/auth/sms/send", json={"phone": phone, "purpose": "login"})
        login = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": phone, "code": "123456"},
        )
        token = login.json()["access_token"]
    else:
        assert reg.status_code == 200, reg.text
        token = reg.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _client() -> TestClient:
    clear_sms_store()
    clear_revoked_sessions()
    clear_context_store()
    return TestClient(create_app())


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def _ask(client: TestClient, headers: dict[str, str], question: str, **extra: object) -> dict:
    resp = client.post(
        "/api/v1/qa/ask",
        headers=headers,
        json={"question": question, "lang": "zh", **extra},
    )
    assert resp.status_code == 200, resp.text
    assert "text/event-stream" in resp.headers.get("content-type", "")
    events = _parse_sse(resp.text)
    assert events, "empty sse"
    assert events[0]["type"] == "meta"
    assert any(e["type"] == "token" for e in events)
    done = next(e for e in events if e["type"] == "done")
    return {"meta": events[0], "done": done, "events": events}


def test_text_ask_auto_context() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131001")

        first = _ask(client, headers, "今天天气怎么样")
        body1 = first["done"]
        assert first["meta"]["context_continued"] is False
        assert body1["context_continued"] is False
        assert body1["context_id"]
        assert body1["question_text"] == "今天天气怎么样"
        assert body1["answer_text"]
        assert body1["turn_index_user"] == 1
        assert body1["turn_index_assistant"] == 2

        second = _ask(client, headers, "那要穿什么衣服？")
        body2 = second["done"]
        assert body2["context_continued"] is True
        assert body2["context_id"] == body1["context_id"]
        assert body2["turn_index_user"] == 3
        assert body2["turn_index_assistant"] == 4


def test_context_ttl_not_extended_on_ask() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131004")
        me = client.get("/api/v1/me", headers=headers)
        user_id = me.json()["id"]

        _ask(client, headers, "第一问")
        expires_after_create = _memory_store[user_id].expires_at

        second = _ask(client, headers, "第二问仍在同一上下文")
        assert second["done"]["context_continued"] is True
        assert _memory_store[user_id].expires_at == expires_after_create


def test_expired_context_creates_new() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131005")
        me = client.get("/api/v1/me", headers=headers)
        user_id = me.json()["id"]

        first = _ask(client, headers, "旧上下文")
        old_id = first["done"]["context_id"]

        _memory_store[user_id].expires_at = 0

        again = _ask(client, headers, "过期后新开")
        assert again["done"]["context_continued"] is False
        assert again["done"]["context_id"] != old_id


def test_text_ask_new_context_flag() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131002")

        first = _ask(client, headers, "血压偏高怎么办")
        cid1 = first["done"]["context_id"]

        forced = _ask(client, headers, "换个话题：今天吃什么", new_context=True)
        assert forced["done"]["context_continued"] is False
        assert forced["done"]["context_id"] != cid1


def test_clear_context() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131003")
        first = _ask(client, headers, "你好")
        cid = first["done"]["context_id"]

        cleared = client.post("/api/v1/qa/context/clear", headers=headers)
        assert cleared.status_code == 200
        assert cleared.json()["ok"] is True
        assert cleared.json()["context_id"] == cid

        again = _ask(client, headers, "重新开始")
        assert again["done"]["context_continued"] is False
        assert again["done"]["context_id"] != cid


def test_sse_token_order() -> None:
    with _client() as client:
        headers = _auth_headers(client, "13100131006")
        result = _ask(client, headers, "流式测试")
        types = [e["type"] for e in result["events"]]
        assert types[0] == "meta"
        assert types[-1] == "done"
        assert "token" in types
        deltas = "".join(e["delta"] for e in result["events"] if e["type"] == "token")
        assert deltas == result["done"]["answer_text"]
