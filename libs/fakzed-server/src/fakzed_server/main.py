"""CLI entry point: `uv run fakzed-server` starts the platform server."""

from __future__ import annotations

import argparse

from fakzed_server.app import FakzedServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Fakzed platform server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="fakzed_server.json", help="JSON persistence file")
    parser.add_argument("--admin-key", default=None, help="bootstrap admin API key")
    parser.add_argument("--no-auth", action="store_true", help="disable API-key auth")
    args = parser.parse_args()

    server = FakzedServer(
        db_path=args.db,
        auth_enabled=not args.no_auth,
        admin_api_key=args.admin_key,
    )

    import uvicorn

    uvicorn.run(server.app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
