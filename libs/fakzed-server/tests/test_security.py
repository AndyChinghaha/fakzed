"""Security tests: rate limiting, CORS, role whitelist, credential hygiene."""

from conftest import ADMIN_KEY, auth_headers
from fastapi.testclient import TestClient

from fakzed_server import FakzedServer, RateLimiter

LIMITED = 3


def make_server(**kwargs) -> FakzedServer:
    return FakzedServer(admin_api_key=ADMIN_KEY, **kwargs)


class TestRateLimit:
    def test_429_after_limit_with_retry_after(self) -> None:
        server = make_server(rate_limit_per_minute=LIMITED)
        client = TestClient(server.app)

        for _ in range(LIMITED):
            assert client.get("/api/agents", headers=auth_headers()).status_code == 200
        blocked = client.get("/api/agents", headers=auth_headers())

        assert blocked.status_code == 429
        assert blocked.headers.get("retry-after") == "60"
        assert "rate limit" in blocked.json()["detail"]

    def test_healthz_exempt(self) -> None:
        server = make_server(rate_limit_per_minute=1)
        client = TestClient(server.app)

        for _ in range(5):
            assert client.get("/healthz").status_code == 200

    def test_buckets_are_per_key(self) -> None:
        server = make_server(rate_limit_per_minute=1)
        client = TestClient(server.app)
        raw2, _ = server.auth.issue(name="second", user_id="u2")
        headers2 = {"X-API-Key": raw2}

        assert client.get("/api/agents", headers=auth_headers()).status_code == 200
        assert client.get("/api/agents", headers=auth_headers()).status_code == 429
        # a different key still has quota
        assert client.get("/api/agents", headers=headers2).status_code == 200

    def test_no_auth_limits_by_ip(self) -> None:
        server = make_server(auth_enabled=False, rate_limit_per_minute=LIMITED)
        client = TestClient(server.app)

        for _ in range(LIMITED):
            assert client.get("/api/agents").status_code == 200
        assert client.get("/api/agents").status_code == 429

    def test_disabled_when_none(self) -> None:
        server = make_server(rate_limit_per_minute=None)
        client = TestClient(server.app)

        for _ in range(10):
            assert client.get("/api/agents", headers=auth_headers()).status_code == 200

    def test_window_slides(self) -> None:
        limiter = RateLimiter(requests_per_minute=2)
        assert limiter.allow("k", now=0.0)
        assert limiter.allow("k", now=1.0)
        assert not limiter.allow("k", now=2.0)
        # 60s later the window slides and quota returns
        assert limiter.allow("k", now=61.0)
        assert limiter.allow("k", now=61.1)


class TestCors:
    def test_wildcard_default(self) -> None:
        client = TestClient(make_server().app)
        response = client.get(
            "/api/agents", headers={**auth_headers(), "Origin": "http://anywhere.example"}
        )
        assert response.headers.get("access-control-allow-origin") == "*"

    def test_explicit_origins_restrict(self) -> None:
        server = make_server(cors_origins=["http://ui.local"])
        client = TestClient(server.app)

        allowed = client.get("/api/agents", headers={**auth_headers(), "Origin": "http://ui.local"})
        assert allowed.headers.get("access-control-allow-origin") == "http://ui.local"

        denied = client.get(
            "/api/agents", headers={**auth_headers(), "Origin": "http://evil.example"}
        )
        assert denied.headers.get("access-control-allow-origin") != "http://evil.example"


class TestKeyIssuance:
    def test_unknown_role_rejected(self) -> None:
        client = TestClient(make_server().app)

        response = client.post(
            "/api/keys", json={"name": "x", "role": "superuser"}, headers=auth_headers()
        )
        assert response.status_code == 400
        assert "role" in response.json()["detail"]

    def test_valid_roles_accepted(self) -> None:
        client = TestClient(make_server().app)

        for role in ("user", "admin"):
            response = client.post(
                "/api/keys", json={"name": f"k-{role}", "role": role}, headers=auth_headers()
            )
            assert response.status_code == 200
            assert response.json()["role"] == role

    def test_bootstrap_seeds_exactly_one_key(self) -> None:
        server = make_server()
        assert len(server.auth.keys) == 1
        assert server.auth.authenticate(ADMIN_KEY).role == "admin"


class TestCredentialHygiene:
    def test_agent_api_key_never_leaks(self) -> None:
        client = TestClient(make_server().app)
        secret = "sk-secret-model-key-123"

        created = client.post(
            "/api/agents",
            json={"name": "leaky", "model": "deepseek:deepseek-chat", "api_key": secret},
            headers=auth_headers(),
        )
        assert created.status_code == 200
        assert secret not in created.text

        listed = client.get("/api/agents", headers=auth_headers())
        assert listed.status_code == 200
        assert secret not in listed.text

        fetched = client.get("/api/agents/leaky", headers=auth_headers())
        assert secret not in fetched.text
        assert "api_key" not in fetched.json()

    def test_issued_key_returned_once_and_hash_hidden(self) -> None:
        server = make_server()
        client = TestClient(server.app)

        issued = client.post("/api/keys", json={"name": "k1"}, headers=auth_headers()).json()
        assert issued["api_key"].startswith("fz_")
        assert "key_hash" not in issued
        stored = server.auth.keys[issued["key_id"]]
        assert stored.key_hash is not None
        assert stored.key_hash not in issued["api_key"]
