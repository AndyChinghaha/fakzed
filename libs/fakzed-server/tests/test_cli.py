"""Tests for the fakzed-server CLI entry point (main.py)."""

from __future__ import annotations

import sys
from typing import Any

import uvicorn

from fakzed_server import main as cli


def _run_cli(argv: list[str], monkeypatch: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run main() with argv and record FakzedServer ctor + uvicorn.run calls."""
    server_kwargs: dict[str, Any] = {}
    uvicorn_kwargs: dict[str, Any] = {}

    captured_app = object()

    def fake_server(**kwargs: Any) -> Any:
        server_kwargs.update(kwargs)
        return type("S", (), {"app": captured_app})()

    def fake_run(app: Any, **kwargs: Any) -> None:
        assert app is captured_app
        uvicorn_kwargs.update(kwargs)

    monkeypatch.setattr(cli, "FakzedServer", fake_server)
    monkeypatch.setattr(uvicorn, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["fakzed-server", *argv])
    cli.main()
    return server_kwargs, uvicorn_kwargs


def test_cli_defaults(monkeypatch: Any) -> None:
    server_kwargs, uvicorn_kwargs = _run_cli([], monkeypatch)

    assert server_kwargs["db_path"] == "fakzed_server.json"
    assert server_kwargs["auth_enabled"] is True
    assert server_kwargs["admin_api_key"] is None
    assert uvicorn_kwargs["host"] == "127.0.0.1"
    assert uvicorn_kwargs["port"] == 8000


def test_cli_full_args(monkeypatch: Any) -> None:
    argv = ["--host", "0.0.0.0", "--port", "9000", "--db", "prod.json", "--admin-key", "secret"]
    server_kwargs, uvicorn_kwargs = _run_cli(argv, monkeypatch)

    assert server_kwargs["db_path"] == "prod.json"
    assert server_kwargs["auth_enabled"] is True
    assert server_kwargs["admin_api_key"] == "secret"
    assert uvicorn_kwargs["host"] == "0.0.0.0"
    assert uvicorn_kwargs["port"] == 9000


def test_cli_no_auth(monkeypatch: Any) -> None:
    server_kwargs, _ = _run_cli(["--no-auth"], monkeypatch)

    assert server_kwargs["auth_enabled"] is False
