"""CLI entry point: `uv run fakzed-server` starts the platform server."""

from __future__ import annotations

import argparse
import os

from fakzed_server.app import FakzedServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Fakzed platform server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default="fakzed_server.json", help="JSON persistence file")
    parser.add_argument(
        "--admin-key",
        default=os.environ.get("FAKZED_ADMIN_KEY"),
        help="bootstrap admin API key (or FAKZED_ADMIN_KEY env var)",
    )
    parser.add_argument("--no-auth", action="store_true", help="disable API-key auth")
    parser.add_argument(
        "--cors-origins",
        default=None,
        help="comma-separated allowed CORS origins (default: * in dev)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=300,
        help="requests per minute per API key/IP (0 disables)",
    )
    args = parser.parse_args()

    cors_origins = args.cors_origins.split(",") if args.cors_origins else None

    if args.no_auth:
        print("WARNING: auth disabled; the API accepts unauthenticated requests")
    if args.rate_limit == 0:
        print("WARNING: rate limiting disabled")

    server = FakzedServer(
        db_path=args.db,
        auth_enabled=not args.no_auth,
        admin_api_key=args.admin_key,
        cors_origins=cors_origins,
        rate_limit_per_minute=args.rate_limit or None,
    )

    import uvicorn

    uvicorn.run(server.app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
