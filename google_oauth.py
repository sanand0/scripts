"""Shared Google OAuth helpers for local scripts.

Exposes `ensure_token(scopes, token_file)` and private, atomic token persistence.

Callers must pass both `scopes` and `token_file` explicitly. This lets callers
use separate users/tokens per script without global defaults.

This module is imported by CLI scripts that declare dependencies via their
`uv run` shebangs, so we avoid importing optional deps at module import time.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def save_token(token_file: Path, serialized: str) -> None:
    """Replace a token atomically with owner-only permissions, including existing files."""
    token_file.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=token_file.parent, prefix=f".{token_file.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(token_file)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_token(*, scopes: list[str], token_file: Path, force_auth: bool = False) -> str:
    """Ensure OAuth creds via InstalledAppFlow; return access token."""
    # Lazy imports to avoid hard dependency unless actually used by a script.
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    cid = os.getenv("GOOGLE_DESKTOP_CLIENT_ID", "").strip()
    csec = os.getenv("GOOGLE_DESKTOP_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        raise RuntimeError("Set GOOGLE_DESKTOP_CLIENT_ID and GOOGLE_DESKTOP_CLIENT_SECRET")

    token_file.parent.mkdir(parents=True, exist_ok=True)

    config = {
        "installed": {
            "client_id": cid,
            "client_secret": csec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost", "http://127.0.0.1"],
        }
    }

    def get_credentials(config, scopes):
        """Get fresh credentials via OAuth flow, persisting in the token file"""
        flow = InstalledAppFlow.from_client_config(config, scopes)
        creds: Credentials | None = flow.run_local_server(port=0, open_browser=True)
        save_token(token_file, creds.to_json())
        return creds

    creds: Credentials | None = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    have_required_scopes = bool(creds and set(scopes).issubset(set(creds.scopes or [])))

    if not creds or not have_required_scopes or force_auth:
        creds = get_credentials(config, scopes)
    elif not creds.valid:
        try:
            creds.refresh(Request())
            save_token(token_file, creds.to_json())
        except RefreshError:
            token_file.unlink(missing_ok=True)
            creds = get_credentials(config, scopes)

    return creds.token if creds else ""


async def api(client: Any, method: str, path: str, **kwargs) -> dict[str, Any]:
    """GET API response as JSON, raising errors."""
    request_fn = getattr(client, method.lower(), None)
    r = await request_fn(path, **kwargs)
    r.raise_for_status()
    return r.json()
