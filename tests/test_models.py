from fastapi.testclient import TestClient

from app.main import create_app


def test_list_models() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/chat/models")

    assert response.status_code == 200
    assert response.json()["data"] == ["echo", "reverse-echo", "openai"]
