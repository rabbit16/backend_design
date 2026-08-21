from fastapi.testclient import TestClient

from src.app.main import create_app


def test_chat_completion() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/chat/completions",
            json={"message": "hello"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "echo"
    assert body["message"] == "echo: hello"
