"""Optional API-key authentication for GPT Actions (`/api/gpt`).

When PROFESSIONAL_PROFILE_API_KEY is unset or empty, requests are allowed
(local/trusted MVP). When set, require Authorization: Bearer <key> or
X-API-Key: <key>.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Header, HTTPException, status


def configured_api_key() -> str | None:
    raw = (os.getenv("PROFESSIONAL_PROFILE_API_KEY") or "").strip()
    return raw or None


async def require_api_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    expected = configured_api_key()
    if expected is None:
        return

    token: str | None = None
    if x_api_key and x_api_key.strip():
        token = x_api_key.strip()
    elif authorization:
        parts = authorization.strip().split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        elif len(parts) == 1:
            token = parts[0].strip()

    if not token or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )
