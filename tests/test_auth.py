from fastapi.testclient import TestClient

from src.app.main import create_app
from src.app.security.jwt import clear_revoked_sessions
from src.app.services.sms_service import clear_sms_store


def _client() -> TestClient:
    clear_sms_store()
    clear_revoked_sessions()
    return TestClient(create_app())


def test_register_flow() -> None:
    with _client() as client:
        send = client.post(
            "/api/v1/auth/sms/send",
            json={"phone": "13500135000", "purpose": "register"},
        )
        assert send.status_code == 200

        bad_code = client.post(
            "/api/v1/auth/register",
            json={
                "phone": "13500135000",
                "code": "000000",
                "password": "secret12",
                "display_name": "毕小雪",
            },
        )
        assert bad_code.status_code == 401
        assert bad_code.json()["code"] == "invalid_sms_code"

        ok = client.post(
            "/api/v1/auth/register",
            json={
                "phone": "13500135000",
                "code": "123456",
                "password": "secret12",
                "display_name": "毕小雪",
                "preferred_lang": "zh",
            },
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["user"]["phone"] == "13500135000"
        assert body["user"]["display_name"] == "毕小雪"
        assert body["access_token"]

        # 重复注册
        client.post(
            "/api/v1/auth/sms/send",
            json={"phone": "13500135000", "purpose": "register"},
        )
        conflict = client.post(
            "/api/v1/auth/register",
            json={"phone": "13500135000", "code": "123456", "password": "secret12"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "phone_already_registered"

        # 注册后可用密码登录
        pwd = client.post(
            "/api/v1/auth/login/password",
            json={"phone": "13500135000", "password": "secret12"},
        )
        assert pwd.status_code == 200


def test_sms_login_flow() -> None:
    with _client() as client:
        send = client.post("/api/v1/auth/sms/send", json={"phone": "13800138000"})
        assert send.status_code == 200
        assert send.json()["ok"] is True
        assert send.json()["expire_in"] == 300

        bad = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": "13800138000", "code": "000000"},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "invalid_sms_code"

        login = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": "13800138000", "code": "123456", "password": "secret1"},
        )
        assert login.status_code == 200
        body = login.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["expires_in"] == 7200
        assert body["user"]["phone"] == "13800138000"
        assert len(body["user"]["id"]) == 36  # UUID CHAR(36)
        assert body["user"]["preferred_lang"] == "zh"

        me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert me.status_code == 200
        assert me.json()["phone"] == "13800138000"


def test_password_login_and_refresh_logout() -> None:
    with _client() as client:
        client.post("/api/v1/auth/sms/send", json={"phone": "13900139000"})
        login = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": "13900139000", "code": "123456", "password": "pass1234"},
        )
        assert login.status_code == 200
        tokens = login.json()

        pwd_login = client.post(
            "/api/v1/auth/login/password",
            json={"phone": "13900139000", "password": "pass1234"},
        )
        assert pwd_login.status_code == 200
        assert pwd_login.json()["user"]["phone"] == "13900139000"

        wrong = client.post(
            "/api/v1/auth/login/password",
            json={"phone": "13900139000", "password": "wrong-pass"},
        )
        assert wrong.status_code == 401
        assert wrong.json()["code"] == "invalid_credentials"

        refreshed = client.post(
            "/api/v1/auth/token/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refreshed.status_code == 200
        new_access = refreshed.json()["access_token"]
        assert new_access

        # 旧 refresh 已随会话作废
        reuse = client.post(
            "/api/v1/auth/token/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert reuse.status_code == 401

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert logout.status_code == 200
        assert logout.json()["ok"] is True

        me = client.get(
            "/api/v1/me",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        assert me.status_code == 401


def test_sms_rate_limited() -> None:
    with _client() as client:
        first = client.post("/api/v1/auth/sms/send", json={"phone": "13700137000"})
        assert first.status_code == 200
        second = client.post("/api/v1/auth/sms/send", json={"phone": "13700137000"})
        assert second.status_code == 429
        assert second.json()["code"] == "sms_rate_limited"


def test_change_password() -> None:
    with _client() as client:
        client.post("/api/v1/auth/sms/send", json={"phone": "13600136000"})
        login = client.post(
            "/api/v1/auth/login/sms",
            json={"phone": "13600136000", "code": "123456", "password": "oldpass1"},
        )
        token = login.json()["access_token"]

        changed = client.post(
            "/api/v1/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"old_password": "oldpass1", "new_password": "newpass1"},
        )
        assert changed.status_code == 200

        ok = client.post(
            "/api/v1/auth/login/password",
            json={"phone": "13600136000", "password": "newpass1"},
        )
        assert ok.status_code == 200
