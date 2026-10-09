# fakzed platform server — uv workspace image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Workspace manifests first (uv cache-friendly layering).
COPY pyproject.toml uv.lock ./
COPY libs/fakzed/pyproject.toml libs/fakzed/pyproject.toml
COPY libs/fakzed/README.md libs/fakzed/README.md
COPY libs/fakzed/LICENSE libs/fakzed/LICENSE
COPY libs/fakzed-server/pyproject.toml libs/fakzed-server/pyproject.toml
COPY libs/fakzed-server/README.md libs/fakzed-server/README.md
COPY libs/fakzed-server/LICENSE libs/fakzed-server/LICENSE

# Sources for both workspace members.
COPY libs/fakzed/src libs/fakzed/src
COPY libs/fakzed-server/src libs/fakzed-server/src

RUN uv sync --frozen --no-dev --package fakzed-server

# fakzed_server.json persisted inside the container by default.
VOLUME ["/data"]

EXPOSE 8000
CMD ["/app/.venv/bin/fakzed-server", "--host", "0.0.0.0", "--port", "8000", "--db", "/data/fakzed_server.json"]
