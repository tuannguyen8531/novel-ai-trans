"""Authentication for the FastAPI app.

Local mode (API_HOST=127.0.0.1) does not require a key. Remote mode
(non-loopback bind) refuses to start without ``API_SECRET_KEY`` and
enforces ``Authorization: Bearer <key>`` on protected endpoints.

The native :class:`fastapi.Request` flow does not read the key from
``Authorization``; SSE clients use a fetch-based wrapper that attaches
the header. See :mod:`src.api.deps` for the request-scoped dependency.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


def is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "::1", "localhost"} or host.startswith("127.")


def is_remote_mode() -> bool:
    return not is_loopback_host(os.getenv("API_HOST", "127.0.0.1"))


def get_secret_key() -> str:
    return os.getenv("API_SECRET_KEY", "")


def require_secret_key_configured() -> None:
    """Called during app startup in remote mode to fail fast on a missing key."""
    if is_remote_mode() and not get_secret_key():
        raise RuntimeError(
            "API_SECRET_KEY must be set when API_HOST is not loopback. Set API_SECRET_KEY or bind to 127.0.0.1 for local use."
        )


def _safe_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@dataclass
class Principal:
    authenticated: bool
    source: str  # "local" | "bearer"


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    parts = header.split(" ", 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def authenticate(request: Request) -> Principal:
    """Resolve the current principal.

    In local mode, the principal is always considered authenticated.
    In remote mode, the request must carry a matching ``Authorization``
    header. Missing or mismatched credentials yield a 401.
    """
    if not is_remote_mode():
        return Principal(authenticated=True, source="local")

    token = _extract_bearer(request)
    expected = get_secret_key()
    if token and expected and _safe_compare(token, expected):
        return Principal(authenticated=True, source="bearer")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "unauthorized", "message": "Authentication required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


def health_authenticate(request: Request) -> Principal:
    """Health endpoint always allows local access; remote mode hides details."""
    if not is_remote_mode():
        return Principal(authenticated=True, source="local")
    return Principal(authenticated=True, source="bearer")
