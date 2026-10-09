"""API key authentication and authorization for the platform API.

Each API key belongs to a user and carries a role. Keys are verified via a
FastAPI dependency that reads the `X-API-Key` header; endpoints opt into
required roles with `require_role("admin")`-style guards.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, PrivateAttr


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(BaseModel):
    """A bearer credential: the raw key is issued once, then stored hashed."""

    key_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str
    user_id: str
    role: str = "user"  # user | admin
    scopes: list[str] = Field(default_factory=list)
    key_hash: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Principal(BaseModel):
    """The authenticated identity attached to a request."""

    user_id: str
    role: str
    key_id: str
    scopes: list[str] = Field(default_factory=list)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiKeyStore(BaseModel):
    """Issues and verifies API keys; keys are only stored as hashes."""

    keys: dict[str, ApiKey] = Field(default_factory=dict)
    _by_hash: dict[str, str] = PrivateAttr(default_factory=dict)

    def issue(
        self,
        *,
        name: str,
        user_id: str,
        role: str = "user",
        scopes: list[str] | None = None,
    ) -> tuple[str, ApiKey]:
        """Create a new key and return (raw_key, record). Store the hash only."""
        raw = "fz_" + secrets.token_hex(24)
        key_hash = hash_key(raw)
        record = ApiKey(
            name=name,
            user_id=user_id,
            role=role,
            scopes=scopes or [],
            key_hash=key_hash,
        )
        self.keys[record.key_id] = record
        self._by_hash[key_hash] = record.key_id
        return raw, record

    def authenticate(self, raw: str | None) -> Principal | None:
        """Resolve a raw key to a Principal, or None if invalid."""
        if not raw:
            return None
        key_id = self._by_hash.get(hash_key(raw))
        if key_id is None:
            return None
        record = self.keys[key_id]
        return Principal(
            user_id=record.user_id,
            role=record.role,
            key_id=record.key_id,
            scopes=record.scopes,
        )

    def revoke(self, key_id: str) -> bool:
        record = self.keys.pop(key_id, None)
        if record is None:
            return False
        if record.key_hash is not None:
            self._by_hash.pop(record.key_hash, None)
        return True
