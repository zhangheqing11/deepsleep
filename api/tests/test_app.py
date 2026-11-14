import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(data_source="mock", cors_origins=("http://localhost:5173",)))
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_health_and_docs_work_without_model_keys(self):
        with patch.dict(os.environ, {"API_DATA_SOURCE": "mock"}, clear=True):
            with TestClient(create_app()) as client:
                response = client.get("/api/v1/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ok", "data_source": "mock", "execution_mode": "mock"})
                self.assertTrue(response.headers["X-Request-ID"].startswith("req_"))
                self.assertEqual(client.get("/docs").status_code, 200)
                schema = client.get("/openapi.json").json()
                self.assertTrue({
                    "/api/v1/health", "/api/v1/runs", "/api/v1/runs/{run_id}",
                    "/api/v1/runs/{run_id}/report", "/api/v1/runs/{run_id}/sessions",
                    "/api/v1/runs/{run_id}/sessions/{visitor_id}",
                }.issubset(schema["paths"]))

    def test_not_found_and_wrong_method_have_error_envelope(self):
        for method, path, status, code in [
            ("GET", "/api/v1/not-a-route", 404, "NOT_FOUND"),
            ("POST", "/api/v1/health", 405, "METHOD_NOT_ALLOWED"),
        ]:
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path)
                self.assertEqual(response.status_code, status)
                error = response.json()["error"]
                self.assertEqual(error["code"], code)
                self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
                if status == 405:
                    self.assertIn("GET", response.headers["Allow"])

    def test_validation_does_not_echo_submitted_value(self):
        @self.app.get("/test-validation")
        async def validation_probe(count: int):
            return {"count": count}

        response = self.client.get("/test-validation", params={"count": "sensitive-test-value"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertNotIn("sensitive-test-value", response.text)

    def test_unhandled_error_is_json_and_has_cors(self):
        @self.app.get("/test-failure")
        async def failure_probe():
            raise RuntimeError("sensitive-test-value")

        with self.assertLogs("api.main", level="ERROR") as captured:
            response = self.client.get("/test-failure", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 500)
        error = response.json()["error"]
        self.assertEqual(error["code"], "INTERNAL_ERROR")
        self.assertEqual(error["request_id"], response.headers["X-Request-ID"])
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5173")
        self.assertNotIn("sensitive-test-value", response.text + str(captured.output))

    def test_cors_allows_configured_origin_and_idempotency_header(self):
        response = self.client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type,Idempotency-Key",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5173")

    def test_unconfigured_origin_gets_no_cors_permission(self):
        response = self.client.get("/api/v1/health", headers={"Origin": "http://unconfigured.example"})
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)


class SettingsTests(unittest.TestCase):
    def test_environment_origins_are_normalized(self):
        environment = {
            "API_CORS_ORIGINS": " http://localhost:5173/,http://localhost:5173,http://127.0.0.1:5173 "
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(
                Settings.from_env().cors_origins,
                ("http://localhost:5173", "http://127.0.0.1:5173"),
            )

    def test_default_has_no_cross_origin_permission(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Settings.from_env().cors_origins, ())

    def test_inconsistent_legacy_mode_fails(self):
        with patch.dict(os.environ, {"API_DATA_SOURCE": "mock", "API_EXECUTION_MODE": "real"}, clear=True):
            with self.assertRaises(ValueError):
                create_app()

    def test_invalid_origins_fail_at_startup(self):
        for origin in [
            "*", "https://*.example.com", "localhost:5173",
            "https://example.com/path", "https://example.com?x=1",
            "https://user@example.com", "http://localhost:99999",
        ]:
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):
                    Settings(data_source="mock", cors_origins=(origin,))


if __name__ == "__main__":
    unittest.main()
