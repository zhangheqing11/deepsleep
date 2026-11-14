"""演示账号登录、Bearer 会话和业务接口保护。"""

from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient

from api.auth import password_digest
from api.config import Settings
from api.main import create_app


class AuthTests(unittest.TestCase):
    def setUp(self):
        settings = Settings(
            data_source="mock",
            cors_origins=("http://localhost:5173",),
            auth_mode="demo",
            auth_username="demo",
            auth_password_sha256=password_digest("demo-pass"),
            auth_ttl_s=60,
            mock_step_delay_s=0.01,
            mock_report_delay_s=0.1,
        )
        self.client = self.enterContext(TestClient(create_app(settings)))

    def test_health_and_login_are_public_but_runs_require_token(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        response = self.client.post("/api/v1/runs", json={"split": "A"}, headers={"Idempotency-Key": "auth-test"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "AUTH_REQUIRED")
        login = self.client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-pass"})
        self.assertEqual(login.status_code, 200)
        body = login.json()
        self.assertEqual(body["user"], {"id": "demo", "display_name": "演示用户", "role": "operator"})
        self.assertEqual(body["token_type"], "bearer")
        self.assertEqual(body["expires_in"], 60)
        self.assertTrue(body["access_token"])

    def test_wrong_password_and_unknown_token_use_uniform_errors(self):
        bad = self.client.post("/api/v1/auth/login", json={"username": "demo", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(bad.json()["error"]["code"], "INVALID_CREDENTIALS")
        unknown = self.client.get("/api/v1/auth/me", headers={"Authorization": "Bearer unknown"})
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(unknown.json()["error"]["code"], "INVALID_TOKEN")
        self.assertEqual(unknown.json()["error"]["request_id"], unknown.headers["X-Request-ID"])

    def test_login_me_run_and_logout(self):
        login = self.client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-pass"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "auth-run"}
        me = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me.json()["authenticated"], True)
        self.assertEqual(me.json()["user"]["id"], "demo")
        created = self.client.post("/api/v1/runs", json={"split": "A"}, headers=headers)
        self.assertEqual(created.status_code, 202)
        logout = self.client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(logout.status_code, 200)
        self.assertEqual(
            self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["error"]["code"],
            "INVALID_TOKEN",
        )

    def test_expired_token_is_rejected(self):
        with patch("api.auth.time.time", return_value=1000):
            login = self.client.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-pass"})
        token = login.json()["access_token"]
        with patch("api.auth.time.time", return_value=1061):
            response = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "TOKEN_EXPIRED")

    def test_cors_preflight_allows_authorization(self):
        response = self.client.options(
            "/api/v1/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertIn("Authorization", response.headers["Access-Control-Allow-Headers"])


class AuthDisabledTests(unittest.TestCase):
    def test_none_mode_preserves_anonymous_mock_compatibility(self):
        with TestClient(create_app(Settings(data_source="mock", mock_step_delay_s=0.01))) as client:
            self.assertEqual(client.get("/api/v1/auth/me").json(), {"authenticated": False, "user": None})
            response = client.post(
                "/api/v1/auth/login", json={"username": "demo", "password": "anything"}
            )
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "AUTH_DISABLED")
            run = client.post(
                "/api/v1/runs", json={"split": "A"}, headers={"Idempotency-Key": "anonymous-auth-test"}
            )
            self.assertEqual(run.status_code, 202)


if __name__ == "__main__":
    unittest.main()
