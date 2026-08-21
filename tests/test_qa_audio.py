"""语音问答（echo 网关）与多模态 schema。"""

from __future__ import annotations

import base64
import json

from fastapi.testclient import TestClient

from src.app.main import create_app
from src.app.schemas.openai_chat import (
    ChatCompletionRequest,
    ChatMessage,
    InputAudio,
    InputAudioContentPart,
    TextContentPart,
)
from src.app.security.jwt import clear_revoked_sessions
from src.app.services.context_store import clear_context_store
from src.app.services.sms_service import clear_sms_store


def _auth_headers(client: TestClient, phone: str = "13100132001") -> dict[str, str]:
    clear_sms_store()
    clear_revoked_sessions()
    clear_context_store()
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


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        line = block.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                events.append(json.loads(payload))
    return events


def test_audio_message_to_openai_param() -> None:
    msg = ChatMessage(
        role="user",
        content=[
            TextContentPart(text="What is in this recording?"),
            InputAudioContentPart(
                input_audio=InputAudio(data="YWJj", format="wav"),
            ),
        ],
    )
    param = msg.to_openai_param()
    assert param["role"] == "user"
    assert param["content"][0]["type"] == "text"
    assert param["content"][1]["type"] == "input_audio"
    assert param["content"][1]["input_audio"]["format"] == "wav"


def test_ask_audio_multipart_sse() -> None:
    fake_wav = b"RIFF....WAVE"
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        resp = client.post(
            "/api/v1/qa/ask/audio",
            headers=headers,
            files={"file": ("q.wav", fake_wav, "audio/wav")},
            data={"lang": "zh", "prompt": "录音里说了什么？"},
        )
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert events[0]["type"] == "meta"
    assert events[0]["input_mode"] == "voice"
    assert any(e["type"] == "token" for e in events)
    done = next(e for e in events if e["type"] == "done")
    assert done["input_mode"] == "voice"
    assert done["answer_text"]


def test_ask_audio_json_sse() -> None:
    encoded = base64.b64encode(b"fake-audio").decode()
    with TestClient(create_app()) as client:
        headers = _auth_headers(client, phone="13100132002")
        resp = client.post(
            "/api/v1/qa/ask/audio/json",
            headers=headers,
            json={
                "audio_base64": encoded,
                "audio_format": "wav",
                "prompt": "请回答",
                "lang": "zh",
            },
        )
    assert resp.status_code == 200, resp.text
    events = _parse_sse(resp.text)
    assert events[0]["type"] == "meta"
    assert next(e for e in events if e["type"] == "done")["answer_text"]


def test_completion_request_modalities() -> None:
    req = ChatCompletionRequest(
        model="gpt-audio",
        messages=[ChatMessage(role="user", content="hi")],
        modalities=["text"],
        stream=True,
    )
    assert req.modalities == ["text"]
