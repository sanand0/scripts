"""Shared Google OAuth helpers for local scripts.

Exposes:
- `client_config_from_env()`: builds InstalledApp client config from env vars
- `ensure_token(scopes, token_file)`: ensures OAuth token for explicit scopes

Callers must pass both `scopes` and `token_file` explicitly. This lets callers
use separate users/tokens per script without global defaults.

This module is imported by CLI scripts that declare dependencies via their
`uv run` shebangs, so we avoid importing optional deps at module import time.
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def ensure_token(*, scopes: List[str], token_file: Path) -> str:
    """Ensure OAuth creds via InstalledAppFlow; return access token."""
    # Lazy imports to avoid hard dependency unless actually used by a script.
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    cid = os.getenv("GOOGLE_DESKTOP_CLIENT_ID", "").strip()
    csec = os.getenv("GOOGLE_DESKTOP_CLIENT_SECRET", "").strip()
    if not cid or not csec:
        raise RuntimeError("Set GOOGLE_DESKTOP_CLIENT_ID and GOOGLE_DESKTOP_CLIENT_SECRET")

    token_file.parent.mkdir(parents=True, exist_ok=True)

    creds: Optional[Credentials] = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes)

    have_required_scopes = bool(creds and set(scopes).issubset(set(creds.scopes or [])))
    if not creds or not have_required_scopes:
        client_config = {
            "installed": {
                "client_id": cid,
                "client_secret": csec,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost", "http://127.0.0.1"],
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, scopes)
        creds = flow.run_local_server(port=0, open_browser=True)
        token_file.write_text(creds.to_json())
    elif not creds.valid:
        creds.refresh(Request())
        token_file.write_text(creds.to_json())
    return creds.token if creds else ""


async def api(client: Any, method: str, path: str, **kwargs) -> Dict[str, Any]:
    """GET API response as JSON, raising errors."""
    request_fn = getattr(client, method.lower(), None)
    r = await request_fn(path, **kwargs)
    r.raise_for_status()
    return r.json()
