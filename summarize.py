#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.9", "google-genai", "openai>=3.28", "pyjwt[crypto]", "python-dotenv", "ruamel.yaml", "rich", "pydantic", "tenacity"]
# ///
"""
Add AI-generated YAML metadata to content files (transcripts, blog posts, etc.).

Content sets are defined in CONTENT_SETS. Each specifies a base directory, AI prompt,
and ordered list of fields to add. The entire file content (including YAML frontmatter)
is sent to the AI so it has full context.

HOW TO ADD A NEW CONTENT SET:
  1. Define FieldDef entries — each needs a name, AI description, Python type, and
     YAML formatter (str, flow_list, or list). Optionally add an extractor (regex
     shortcut before calling the AI) and a cleaner (normalize AI output).
  2. Append a ContentSet to CONTENT_SETS with name, base_dir, prompt, fields, and
     default_globs (patterns expanded against base_dir when no CLI patterns are given).
  3. No other code changes required.

Usage:
  uv run summarize.py transcript                             # all transcripts in base dir
  uv run summarize.py transcript "2026-04-*.md"              # relative glob (resolved from .)
  uv run summarize.py transcript "/other/path/*.md"          # absolute glob
  uv run summarize.py blog                                   # all blog posts/pages
  uv run summarize.py blog "2026-*.md"                       # relative glob
  uv run summarize.py --dry-run transcript "2026-04-*.md"    # preview changes
  uv run summarize.py --workers 8 transcript "*.md"          # 8 parallel workers
  uv run summarize.py --force transcript "2026-04-*.md"      # re-process all fields
  uv run summarize.py login chatgpt --paste                   # sign in from another device
  uv run summarize.py blog post.md --provider chatgpt         # use the saved ChatGPT plan
"""

import base64
import concurrent.futures
import fcntl
import getpass
import glob as glob_module
import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import StringIO
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

import typer
from dotenv import dotenv_values, load_dotenv
from pydantic import Field as PydanticField
from pydantic import create_model
from rich.console import Console
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq
from tenacity import retry, stop_after_attempt, wait_exponential

app = typer.Typer(add_completion=False, pretty_exceptions_show_locals=False)
console = Console(stderr=True)
_print_lock = Lock()
MIN_CONTENT_LINES = 5

# Pricing in $ per 1M tokens (input, output) — update as needed
PRICING: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash":       (1.50,  7.50),
    "gemini-3.7-flash":       (1.50,  7.50),
    "gemini-3.5-flash":       (1.50,  9.00),
    "gemini-3.1-flash-lite":  (0.25,  1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3-flash-preview": (0.075, 0.30),
    "gemini-3-pro-preview":   (1.25,  5.00),
    "gemini-2.5-flash":       (0.075, 0.30),
    "gemini-2.5-pro":         (1.25,  5.00),
    "gemini-2.0-flash":       (0.075, 0.30),
    "gpt-6-luna":             (0.10,  0.60),
    "gpt-5.6-luna":           (0.20,  1.20),
}
# Default price if user specifies a model not in PRICING dict
DEFAULT_PRICING = (1.50,  7.50)
LUNA_MODEL = "gpt-6-luna"
DEFAULT_MODELS = {"gemini": "gemini-3.8-flash", "openai": LUNA_MODEL, "chatgpt": LUNA_MODEL}

CHATGPT_STATE = Path.home() / ".cache/sanand-scripts/summarize/chatgpt"
CHATGPT_ISSUER = "https://auth.openai.com"
CHATGPT_RESOURCE = "https://api.openai.com/v1"
CHATGPT_SCOPE = "chatgpt.tokens.use.direct"
CHATGPT_SCOPES = f"openid profile email offline_access resource.invoke {CHATGPT_SCOPE}"
CHATGPT_REGISTER = "dynamic_agent_client"
CHATGPT_CALLBACK = "/auth/callback"
CHATGPT_LOGIN = "summarize.py login chatgpt"


class ChatGPTError(ValueError):
    pass


class ChatGPTGrantError(ChatGPTError):
    pass


class ChatGPTDeniedError(ChatGPTError):
    pass


def save_chatgpt_state(path: Path, value: dict | str) -> None:
    """Replace each state record atomically. NamedTemporaryFile starts at mode 0600."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as tmp:
        pending = Path(tmp.name)
        try:
            json.dump(value, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp.close()
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)


def chatgpt_records() -> dict[str, Path]:
    return {f"{path.parent.name}/{path.stem}": path for path in CHATGPT_STATE.glob("*/*.json")}


def chatgpt_record(account: str | None) -> Path | None:
    if account is None:
        active = CHATGPT_STATE / "active"
        if not active.exists():
            return None
        account = json.loads(active.read_text())
    path = chatgpt_records().get(account)
    if path is None:
        raise ChatGPTError(f"Unknown ChatGPT account '{account}'. Run {CHATGPT_LOGIN} --accounts.")
    return path


def chatgpt_exchange(client_id: str, **grant: str) -> dict:
    request = Request(
        f"{CHATGPT_ISSUER}/api/accounts/oauth/token",
        data=urlencode(dict(client_id=client_id, resource=CHATGPT_RESOURCE, **grant)).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=20) as response:
            tokens = json.load(response)
    except HTTPError as exc:
        try:
            code = json.load(exc).get("error")
        except (ValueError, AttributeError):
            code = None
        if code in {"invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
                    "refresh_token_invalidated", "refresh_token_reused"}:
            raise ChatGPTGrantError(f"ChatGPT OAuth returned {code}.") from None
        reason = " (invalid_client)" if code == "invalid_client" else ""
        raise ChatGPTError(f"ChatGPT token exchange returned HTTP {exc.code}{reason}.") from None
    except (URLError, TimeoutError):
        raise ChatGPTError("Could not reach the ChatGPT token endpoint. Try again.") from None
    if not tokens.get("access_token") or tokens.get("token_type", "").lower() != "bearer":
        raise ChatGPTError("ChatGPT OAuth did not return a bearer access token.")
    return tokens


def chatgpt_token_fields(tokens: dict) -> dict:
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "scopes": tokens["scope"].split(),
        "expires_at": time.time() + int(tokens["expires_in"]),
    }


def chatgpt_identity(id_token: str, client_id: str, nonce: str) -> dict:
    import jwt

    try:
        jwks = jwt.PyJWKClient(f"{CHATGPT_ISSUER}/.well-known/jwks.json", timeout=15)
        key = jwks.get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=client_id,
                            issuer=CHATGPT_ISSUER, leeway=15,
                            options={"require": ["exp", "sub", "nonce", "email"]})
    except jwt.PyJWTError:
        raise ChatGPTError("Could not validate the ChatGPT ID token.") from None
    if claims["nonce"] != nonce or not isinstance(claims["email"], str) or "@" not in claims["email"]:
        raise ChatGPTError("ChatGPT ID token did not match the sign-in attempt.")
    return {"issuer": claims["iss"], "subject": claims["sub"], "email": claims["email"]}


def chatgpt_callback(url: str, redirect_uri: str, state: str, client_id: str) -> tuple[str, str]:
    received = urlsplit(url)
    if received._replace(query="").geturl() != redirect_uri:
        raise ChatGPTError("Paste the full callback URL shown in the browser address bar.")
    params = parse_qs(received.query, keep_blank_values=True)
    if params.get("state") != [state]:
        raise ChatGPTError("ChatGPT callback state did not match this sign-in attempt.")
    if "error" in params:
        raise ChatGPTDeniedError("ChatGPT sign-in was declined or failed in the browser.")
    codes = params.get("code", [""])
    client_ids = params.get("client_id", [client_id])
    if len(codes) != 1 or len(client_ids) != 1:
        raise ChatGPTError("ChatGPT callback contained duplicate fields.")
    code, issued_id = codes[0], client_ids[0]
    if (not code or not re.fullmatch(r"[A-Za-z0-9_-]+", issued_id) or issued_id == CHATGPT_REGISTER
            or client_id not in {issued_id, CHATGPT_REGISTER}):
        raise ChatGPTError("ChatGPT callback did not include a valid code and client ID.")
    return code, issued_id


def authorize_chatgpt(host_id: str, saved: dict, paste: bool) -> dict:
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    client_id = saved.get("client_id", CHATGPT_REGISTER)
    callback: list[tuple[str, str]] = []
    denied: list[ChatGPTDeniedError] = []

    class Receiver(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                callback.append(chatgpt_callback(f"http://127.0.0.1:{self.server.server_port}{self.path}",
                                                 redirect_uri, state, client_id))
            except ChatGPTDeniedError as exc:
                denied.append(exc)
                self.send_error(400, "ChatGPT sign-in was declined or failed in the browser.")
                return
            except ValueError:
                self.send_error(400, "ChatGPT callback was not accepted. Return to the terminal.")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ChatGPT authorization received. Return to the terminal to finish sign-in.")

        def log_message(self, *args):
            pass  # The request URL contains the authorization code.

    with HTTPServer(("127.0.0.1", 0), Receiver) as server:
        redirect_uri = f"http://127.0.0.1:{server.server_port}{CHATGPT_CALLBACK}"
        params = dict(client_id=client_id, ext_agent_host_id=host_id, redirect_uri=redirect_uri,
                      scope=CHATGPT_SCOPES, resource=CHATGPT_RESOURCE, response_type="code",
                      state=state, nonce=nonce, code_challenge=challenge, code_challenge_method="S256")
        if not saved:
            params["agent_name_hint"] = "summarize.py"
        elif CHATGPT_SCOPE not in saved["scopes"]:
            params["prompt"] = "consent"
        # Leave out the optional ID-token hint so the URL can be relayed to another device.
        typer.echo(f"Continue with ChatGPT\n{CHATGPT_ISSUER}/api/accounts/authorize?{urlencode(params)}", err=True)
        if paste:
            typer.echo("After approving, copy the full redirected URL from the address bar, even if the page cannot load.", err=True)
            url = getpass.getpass("Callback URL: ") if sys.stdin.isatty() else sys.stdin.readline()
            code, issued_id = chatgpt_callback(url.strip(), redirect_uri, state, client_id)
        else:
            typer.echo("Approve in a browser on this machine or use --paste for a browser on another device.", err=True)
            deadline = time.monotonic() + 600
            while not (callback or denied) and (remaining := deadline - time.monotonic()) > 0:
                server.timeout = remaining
                server.handle_request()
            if denied:
                raise denied[0]
            if not callback:
                raise ChatGPTError("ChatGPT sign-in timed out. Start a new sign-in.")
            code, issued_id = callback[0]

    tokens = chatgpt_exchange(issued_id, grant_type="authorization_code", code=code,
                              code_verifier=verifier, redirect_uri=redirect_uri)
    identity = chatgpt_identity(tokens.get("id_token", ""), issued_id, nonce)
    if saved and saved["subject"] != identity["subject"]:
        raise ChatGPTError("ChatGPT signed in to a different account. The saved account was kept.")
    return {**identity, "client_id": issued_id, "ext_agent_host_id": host_id,
            "id_token": tokens["id_token"], **chatgpt_token_fields(tokens)}


def login_chatgpt(account: str | None, paste: bool, new: bool, accounts: bool) -> None:
    if accounts:
        if account or paste or new:
            raise ChatGPTError("Use --accounts by itself to list saved accounts.")
        active = chatgpt_record(None)
        for label, path in sorted(chatgpt_records().items()):
            typer.echo(f"{label}\t{'active' if path == active else 'saved'}")
        return
    if new and account:
        raise ChatGPTError("Choose either --new-account or an existing --account.")
    CHATGPT_STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (CHATGPT_STATE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        host_file = CHATGPT_STATE / "host-id"
        if not host_file.exists():
            save_chatgpt_state(host_file, f"urn:uuid:{uuid4()}")
        host_id = json.loads(host_file.read_text())
    existing = None if new else chatgpt_record(account)
    saved = json.loads(existing.read_text()) if existing else {}
    record = authorize_chatgpt(host_id, saved, paste)
    label = f"{quote(record['email'], safe='@.+')}/{record['client_id']}"
    path = existing or CHATGPT_STATE / f"{label}.json"
    label = f"{path.parent.name}/{path.stem}"
    plan_enabled = CHATGPT_SCOPE in record["scopes"]
    with (CHATGPT_STATE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        save_chatgpt_state(path, record)
        if plan_enabled:
            save_chatgpt_state(CHATGPT_STATE / "active", label)
    if not plan_enabled:
        raise ChatGPTError(f"Signed in as {record['email']}. Run {CHATGPT_LOGIN} --account {label} to allow ChatGPT plan usage.")
    typer.echo(f"Signed in with ChatGPT as {record['email']}.", err=True)


def chatgpt_access_token(path: Path | None) -> str:
    if path is None:
        raise ChatGPTError(f"No ChatGPT session. Run {CHATGPT_LOGIN} first.")
    record = json.loads(path.read_text())
    sign_in = f"{CHATGPT_LOGIN} --account {path.parent.name}/{path.stem}"
    if CHATGPT_SCOPE not in record["scopes"]:
        raise ChatGPTError(f"ChatGPT plan permission is missing. Run {sign_in}.")
    if record.get("access_token") and record["expires_at"] > time.time() + 60:
        return record["access_token"]
    with (CHATGPT_STATE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # Refresh tokens rotate, including across worker processes.
        record = json.loads(path.read_text())
        if CHATGPT_SCOPE not in record["scopes"]:
            raise ChatGPTError(f"ChatGPT plan permission is missing. Run {sign_in}.")
        if record.get("access_token") and record["expires_at"] > time.time() + 60:
            return record["access_token"]
        if not record.get("refresh_token"):
            raise ChatGPTError(f"ChatGPT session expired. Run {sign_in}.")
        try:
            tokens = chatgpt_exchange(record["client_id"], grant_type="refresh_token",
                                      refresh_token=record["refresh_token"])
        except ChatGPTGrantError as exc:
            save_chatgpt_state(path, {**record, "access_token": None, "refresh_token": None, "id_token": None})
            raise ChatGPTError(f"{exc} Run {sign_in}.") from None
        updated = {**record, **chatgpt_token_fields(tokens)}
        save_chatgpt_state(path, updated)
        if CHATGPT_SCOPE not in updated["scopes"]:
            raise ChatGPTError(f"ChatGPT plan permission is missing. Run {sign_in}.")
        return updated["access_token"]


# ── Field definition ────────────────────────────────────────────────────────────

@dataclass
class FieldDef:
    """Configuration for one YAML metadata field within a content set.

    Fields:
        name:          YAML key (e.g. "summary", "keywords")
        description:   Instruction embedded in the AI schema for this field
        pydantic_type: Python type annotation: str or list[str]
        to_yaml:       Converts the value for YAML: use str, flow_list, or list
        extract:       Optional (body: str) -> list; non-empty result skips AI call
        clean:         Optional normalizer applied to AI output before saving
    """
    name: str
    description: str
    pydantic_type: Any
    to_yaml: Callable
    extract: Callable[[str], list] | None = None
    clean: Callable[[Any], Any] | None = None


# ── Content set definition ──────────────────────────────────────────────────────

@dataclass
class ContentSet:
    """All configuration for one content type. See module docstring to add new sets."""
    name: str
    base_dir: Path
    prompt: str
    fields: list[FieldDef]
    default_globs: list[str] = field(default_factory=lambda: ["*.md"])
    exclude_names: list[str] = field(default_factory=list)  # basenames to skip (e.g. SKILL.md)
    meta_position: str = "before"  # "before": meta keys first; "after": meta keys last
    skip_if: Callable[[str], str | None] | None = None
    prompt_builder: Callable[[str, list[FieldDef] | None], str] | None = None
    default_workers: int = 4

    @property
    def meta_keys(self) -> list[str]:
        return [f.name for f in self.fields]

    def prompt_for(self, text: str, fields: list["FieldDef"] | None = None) -> str:
        return self.prompt_builder(text, fields) if self.prompt_builder else self.prompt


# ── YAML helpers ───────────────────────────────────────────────────────────────

def make_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 100000
    y.representer.add_representer(
        type(None),
        lambda d, _: d.represent_scalar("tag:yaml.org,2002:null", ""),
    )
    return y


def flow_list(items: list) -> CommentedSeq:
    cs = CommentedSeq(items)
    cs.fa.set_flow_style()
    return cs


def parse_frontmatter(text: str) -> tuple[dict, str, bool]:
    if not text.startswith("---"):
        return {}, text, False
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text, False
    data = make_yaml().load(text[3:end]) or {}
    body = text[end + 4:].lstrip("\n")
    return data, body, True


def dump_metadata(metadata: dict) -> str:
    stream = StringIO()
    make_yaml().dump(metadata, stream)
    return stream.getvalue()


def without_frontmatter_fields(text: str, names: set[str]) -> str:
    """Remove fields being regenerated so old AI output cannot anchor the new call."""
    metadata, body, had_fm = parse_frontmatter(text)
    if not had_fm:
        return text
    for name in names:
        metadata.pop(name, None)
    return f"---\n{dump_metadata(metadata)}---\n\n{body}"


def strip_empty_values(metadata: dict) -> CommentedMap:
    """Remove keys whose value is None or empty string (keep empty lists — meaningful)."""
    result = CommentedMap()
    for key, val in metadata.items():
        if val is None or (isinstance(val, str) and not val.strip()):
            continue
        result[key] = val
    return result


def write_file(
    path: Path,
    had_fm: bool,
    original_text: str,
    updates: dict,
    meta_position: str,
    full_metadata: dict | None = None,
) -> None:
    """Write metadata updates to file.

    Normal mode (full_metadata=None): text-based insertion — serializes only the new
    keys and appends/prepends them to the existing frontmatter text verbatim.  Existing
    keys are never re-serialized, so their formatting (flow-map spaces, sequence
    indentation, quoting, etc.) is preserved exactly.

    Force mode (full_metadata provided): re-serializes the entire frontmatter from the
    parsed dict.  Formatting of existing keys may change.
    """
    if full_metadata is not None:
        new_fm = dump_metadata(strip_empty_values(full_metadata))
        if had_fm:
            end = original_text.find("\n---", 3)
            after_content = original_text[end + 4:].lstrip("\n")
            new_text = f"---\n{new_fm}---\n\n{after_content}"
        else:
            new_text = f"---\n{new_fm}---\n\n{original_text.lstrip(chr(10))}"
    else:
        new_data = CommentedMap()
        for key, val in updates.items():
            if val is not None and not (isinstance(val, str) and not val.strip()):
                new_data[key] = val
        new_keys_text = dump_metadata(new_data)
        if had_fm:
            end = original_text.find("\n---", 3)
            existing_fm = original_text[4:end + 1]  # preserves original text + trailing \n
            after_content = original_text[end + 4:].lstrip("\n")
            new_fm = (existing_fm + new_keys_text) if meta_position == "after" else (new_keys_text + existing_fm)
            new_text = f"---\n{new_fm}---\n\n{after_content}"
        else:
            new_text = f"---\n{new_keys_text}---\n\n{original_text.lstrip(chr(10))}"
    path.write_text(new_text, encoding="utf-8")


def reorder_metadata(old: dict, updates: dict, meta_keys: list[str], meta_position: str = "before") -> CommentedMap:
    """Build CommentedMap with meta_keys placed before or after existing keys."""
    result = CommentedMap()
    if meta_position == "after":
        for key, val in old.items():
            if key not in meta_keys:
                result[key] = val
        for key in meta_keys:
            val = updates.get(key, old.get(key))
            if val is not None:
                result[key] = val
    else:  # "before"
        for key in meta_keys:
            val = updates.get(key, old.get(key))
            if val is not None or key in old:
                result[key] = val
        for key, val in old.items():
            if key not in result:
                result[key] = val
    return result


# ── Speaker extraction helpers (transcript-specific) ──────────────────────────

# Keep these semantic (roles / analysis structure), never entity-specific names or phrases.
_GENERIC_SPEAKER_LABELS = {
    "all", "cashier", "doctor", "everyone", "facilitator", "faculty", "group", "host",
    "human", "client", "professor", "server", "sme", "someone", "source", "student", "students", "teacher", "unknown",
    "unsure", "waiter", "waitress", "woman", "you",
}
_ROLE_ENDINGS = {
    "assistant", "attendee", "attendees", "audience", "audio", "interviewer", "lead", "member",
    "members", "moderator", "narration", "narrator", "panelist", "panelists", "participant",
    "participants", "partner", "presenter", "presenters", "rep", "researcher", "researchers", "speaker",
    "speakers", "staff", "team", "tech", "video", "voice", "voiceover",
}
_META_STARTS = {"better", "how", "invalid", "key", "next", "notes", "possible", "possibly-invalid", "potentially", "references", "step", "then", "try", "what", "why"}
_META_WORDS = {
    "action", "actions", "answer", "assumption", "assumptions", "behavior", "belief", "beliefs", "change", "correction",
    "corrections", "engagement", "error", "impact", "insight", "insights", "intent", "iteration",
    "measurable", "meta-insight", "miss", "move", "outcome", "persona", "phrasing", "prompt",
    "question", "quote", "reason", "recap", "response", "strategy", "summary", "takeaways",
}


def _is_analysis_label(words: list[str]) -> bool:
    if not words:
        return False
    if len(words) == 1:
        return words[0] in _META_WORDS
    if words[0] in _META_STARTS or words[0] in _META_WORDS:
        return True
    if words[0] in {"the", "their", "your", "his", "her", "my", "our"} and words[-1] in _META_WORDS:
        return True
    if (words[0].endswith("'s") or words[0].endswith("’s")) and words[-1] in _META_WORDS:
        return True
    return words[:2] == ["to", "recap"]


def _is_real_name_part(name: str) -> bool:
    """Reject generic role / analysis labels without substring-matching real names."""
    normalized = name.casefold().strip()
    words = re.findall(r"[\w’'.-]+", normalized)
    return (
        bool(words)
        and not name.startswith("[")
        and "implied" not in words
        and not re.search(r"\s\d+$", name)
        and normalized not in _GENERIC_SPEAKER_LABELS
        and words[0] not in _ROLE_ENDINGS
        and words[-1] not in _ROLE_ENDINGS
        and not _is_analysis_label(words)
        and not (len(words) > 1 and words[-1] in {"ai", "bot"})
        and not any(marker in name for marker in (" + ", " ↔ ", " -> ", " → ", " & "))
    )


def _is_real_name(name: str) -> bool:
    parts = [part.strip() for part in re.split(r"\s*/\s*", name)]
    return len(parts) <= 3 and all(_is_real_name_part(part) for part in parts)


def _clean_name(raw: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", str(raw)).strip()


def extract_speakers(body: str) -> list[str]:
    """Extract bold speaker labels from the transcript section, ignoring analysis before it."""
    match = re.search(r"^#{1,4}\s+Transcript\b.*$", body, re.MULTILINE | re.IGNORECASE)
    transcript = body[match.end():] if match else body
    names = (
        _clean_name(raw)
        for raw in re.findall(r"^[ \t]{0,3}\*\*([^*:\n]+?)(?:\*\*\s*:|:\*\*)", transcript, re.MULTILINE)
    )
    return list(dict.fromkeys(n for n in names if _is_real_name(n)))


def clean_people(people: list) -> list[str]:
    return [_clean_name(n) for n in people if _is_real_name(_clean_name(str(n).strip()))]


def clean_ideas(ideas: list) -> list[str]:
    """Strip a leading '#IDEA' tag / stray quotes the model may echo from the notes."""
    out = []
    for raw in ideas:
        s = re.sub(r"^\s*#idea[:\s-]*", "", str(raw).strip(), flags=re.IGNORECASE).strip(" '\"")
        if s:
            out.append(s)
    return out


def clean_what_i_missed(items: list) -> list[str]:
    """Normalize the deliberately small reason taxonomy used by what-i-missed."""
    aliases = {
        "topic": "topic shift",
        "focus": "task focus",
        "solution": "premature solution mode",
        "time": "time pressure",
        "pace": "pace",
        "dominance": "conversational dominance",
    }
    out = []
    for raw in items:
        item = str(raw).strip()
        match = re.search(r"(?i)(Possible reason:\s*)([^.]+)(\.?)$", item)
        if match:
            reason = match.group(2).strip().lower()
            allowed = next((value for value in aliases.values() if value in reason), None)
            if allowed is None:
                allowed = next((value for key, value in aliases.items() if key in reason), "task focus")
            item = item[:match.start()] + match.group(1) + allowed + "."
        if item:
            out.append(item)
    return out


# ── Blog tag helpers ──────────────────────────────────────────────────────────

BLOG_TAGS_PATH = Path("/home/sanand/code/blog/metadata-tags.yml")
BLOG_PROPOSALS_PATH = BLOG_TAGS_PATH.with_name("metadata-tag-proposals.yml")
TAG_TOKEN_RE = re.compile(r"[a-z0-9]+")
MAX_BLOG_TAG_CANDIDATES = 80
COMMON_BLOG_TAGS = 25


def _tag_slug(value: str) -> str:
    text = str(value).strip().lower()
    text = text.replace("&", " and ").replace("+", " plus ").replace("'", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    aliases = {
        "large-language-model": "llms",
        "large-language-models": "llms",
        "llm": "llms",
        "visualisation": "data-visualization",
        "visualization": "data-visualization",
        "data-visualisation": "data-visualization",
        "dataviz": "data-visualization",
        "books": "book",
        "genai": "generative-ai",
        "gen-ai": "generative-ai",
    }
    return aliases.get(text, text)


@lru_cache(maxsize=1)
def blog_tag_vocabulary() -> tuple[dict[str, dict], dict[str, str]]:
    data = make_yaml().load(BLOG_TAGS_PATH.read_text(encoding="utf-8")) or {}
    tags = data.get("tags") or {}
    alias_map: dict[str, str] = {}
    for tag, details in tags.items():
        alias_map[_tag_slug(tag)] = tag
        for alias in details.get("aliases") or []:
            alias_map[_tag_slug(str(alias))] = tag
    return tags, alias_map


def _tokens(text: str) -> set[str]:
    return set(TAG_TOKEN_RE.findall(text.lower()))


def blog_tag_candidates(text: str, limit: int = MAX_BLOG_TAG_CANDIDATES) -> list[str]:
    tags, _ = blog_tag_vocabulary()
    doc_tokens = _tokens(text)
    scored: list[tuple[int, int, str]] = []
    for tag, details in tags.items():
        tag_text = " ".join([tag, details.get("description") or "", *[str(a) for a in details.get("aliases") or []]])
        overlap = len(doc_tokens & _tokens(tag_text))
        count = int(details.get("count") or 0)
        if overlap:
            scored.append((overlap, count, tag))
    candidates = [tag for _, _, tag in sorted(scored, key=lambda item: (-item[0], -item[1], item[2]))[:limit]]
    for tag in list(tags)[:COMMON_BLOG_TAGS]:
        if tag not in candidates:
            candidates.append(tag)
    return candidates[:limit]


def blog_prompt(text: str, fields: list[FieldDef] | None = None) -> str:
    field_names = {field.name for field in (fields or [])} or {"description", "tags"}
    parts: list[str] = []
    if field_names == {"description"}:
        parts.append("Generate only a description for this blog post's metadata.")
    elif field_names == {"tags"}:
        parts.append("Generate only canonical tags for this blog post's metadata.")
    else:
        parts.append("Generate a description and canonical tags for this blog post's metadata.")

    if "description" in field_names:
        parts.append(
            "Description: write for a human scanning Anand's blog. The same text should identify the page well for "
            "search or an LLM agent, but optimize the prose for the human. Aim for 25-35 words; 20-40 is fine. Use "
            "1-2 short sentences; shorter is better once the reader has a clear mental picture. Use first person when "
            "the post records something I did, found, tried, learned, measured, or think. A link post can simply start "
            "'I found a page...'. Use simple words, active voice, and wording close to the source. Avoid dense "
            "abstractions, formal metadata language, and invented synthesis. Concrete is good, density is bad: use names, "
            "numbers, results, tools, or examples only when they make the idea easier to picture or distinguish the post, "
            "not to prove coverage. Classify the post by what Anand wrote, not by how many examples appear in a linked "
            "source. Roundup: at most 4 short highlights, prioritizing distinctive/personal x surprising over comprehensive "
            "or merely important coverage. Concept/opinion: state the idea simply; if the source contains a list of "
            "examples or applications, do not compress that list - pick at most one representative example. Workflow: "
            "say what I do; if there are several methods, keep at most 3 central ones, otherwise use one example or "
            "payoff. Link/discovery: say what I found, then at most 2 illustrative findings even if the linked page has a "
            "long list. Contrast/ranking: preserve the baseline and the standout result when that comparison is the insight, rather than two secondary examples. Story/puzzle: preserve both "
            "the concrete action and the inference connecting it to the outcome - what the action lets someone conclude or prove; do not replace the inference with the "
            "moral. Survey/data result: state the simple pattern first; use at most one number or example unless a contrast "
            "requires two. Forecast: state the premise and one or two consequences, not a long implication list. Never "
            "list more than 3 parallel capabilities/actions. Before answering, count independent examples/subtopics and "
            "cut extras to these limits. For any example, state what happened or was found, not merely its setup. Omission "
            "is a feature. Silently verify every remaining concrete fact against the source. Use ASCII punctuation."
        )

    if "tags" in field_names:
        tags, _ = blog_tag_vocabulary()
        tag_lines = "\n".join(
            f"- {tag} ({int(tags[tag].get('count') or 0)} posts): "
            f"{tags[tag].get('description', '').removeprefix('Posts about ').rstrip('.')}"
            for tag in blog_tag_candidates(text)
        )
        parts.append(
            "Tags: choose 2-4 canonical tags for both human related-post navigation and machine clustering. Infer "
            "concepts semantically, not just from repeated words. First capture the organizing question or lens, then "
            "only substantial facets such as domain or named tool. Examples of lens mapping: extrapolating "
            "a trend into future outcomes -> forecasting; examining a dataset -> data-analysis; checking claims against "
            "sources -> fact-checking/verification; solving a constrained puzzle -> problem-solving. Do not tag a "
            "setting, downstream example, or memorable detail unless it is a major independent subject. Avoid a generic "
            "parent when a specific tag already identifies the subject, and avoid synonyms or near-duplicates. Prefer "
            "established accurate clusters; counts show size, but relevance wins. The shortlist is "
            "not exhaustive: emit an obvious conventional slug if missing; known tags canonicalize, unknown ones "
            f"are flagged for review.\n\nCandidate canonical tag shortlist:\n{tag_lines}"
        )

    return "\n\n".join(parts) + "\n\n"


def split_blog_tags(values: Any) -> tuple[list[str], list[str]]:
    """Return canonical tags and normalized proposals without mixing the two."""
    _, aliases = blog_tag_vocabulary()
    tags: list[str] = []
    proposals: set[str] = set()
    for raw in values or []:
        item = str(raw).strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered.startswith("proposed:"):
            if proposal := _tag_slug(item.split(":", 1)[1]):
                proposals.add(proposal)
            continue
        tag = aliases.get(_tag_slug(item))
        if tag and tag not in tags:
            tags.append(tag)
        elif item:
            if proposal := _tag_slug(item):
                proposals.add(proposal)
    return tags, sorted(proposals)


def clean_blog_tags(values: Any) -> list[str]:
    tags, proposals = split_blog_tags(values)
    if proposals:
        console.print(f"[yellow]Proposed blog tags retained for review: {proposals}[/yellow]")
    return tags


def _atomic_yaml_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            make_yaml().dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def merge_blog_tag_proposals(path: Path, evidence: list[dict]) -> None:
    """Reconcile processed sources into the proposal ledger with one atomic write."""
    existing = make_yaml().load(path.read_text(encoding="utf-8")) if path.exists() else {}
    proposals = (existing or {}).get("proposals") or {}
    processed_sources = {item["source"] for item in evidence}
    merged: dict[str, dict[str, dict[str, str]]] = {}
    for proposal, details in proposals.items():
        sources = {
            source: dict(source_details)
            for source, source_details in (details.get("sources") or {}).items()
            if source not in processed_sources
        }
        if sources:
            merged[str(proposal)] = {"sources": sources}
    for item in evidence:
        source_details = {"content_hash": item["content_hash"]}
        for proposal in sorted(set(item.get("proposals") or [])):
            merged.setdefault(proposal, {"sources": {}})["sources"][item["source"]] = source_details
    normalized = {
        proposal: {"sources": dict(sorted(details["sources"].items()))}
        for proposal, details in sorted(merged.items())
    }
    _atomic_yaml_write(path, {"version": 1, "proposals": normalized})


def blog_source_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


# ── Shared helpers ─────────────────────────────────────────────────────────────

def is_unprocessed(val: Any) -> bool:
    """Needs AI if None/missing/empty-string. Empty list [] = processed-but-empty."""
    return val is None or (isinstance(val, str) and not val.strip())


def count_content_lines(text: str) -> int:
    return sum(1 for ln in text.splitlines() if (s := ln.strip()) and not s.startswith("#"))


MIN_TRANSCRIPT_CHARS = 200


def _transcript_skip(body: str) -> str | None:
    """Skip if ## Transcript section is missing or under MIN_TRANSCRIPT_CHARS chars."""
    m = re.search(r'^## Transcript\s*$', body, re.MULTILINE)
    if not m or len(body[m.end():].strip()) < MIN_TRANSCRIPT_CHARS:
        return "empty transcript"
    return None


# ── Content set registry ───────────────────────────────────────────────────────
# To add a new content set: define FieldDefs and append a ContentSet below.

CONTENT_SETS: list[ContentSet] = [
    ContentSet(
        name="transcript",
        base_dir=Path("/home/sanand/Dropbox/notes/transcripts"),
        prompt=(
            "Analyze this meeting transcript and extract only the requested metadata fields. "
            "Use only transcript evidence. Treat a leading YYYY-MM-DD in the title as the meeting date. "
            "Be conservative: false positives are worse than omissions. Never invent dates, channels, recipients, "
            "cc lists, deliverables, commitments, workflow details, motives, or emotional states. When evidence is "
            "insufficient, omit the detail. Before output, silently falsify every item against later transcript evidence.\n\n"
            "For 'people': include only clearly named speakers — no placeholders.\n"
            "For 'ideas': capture forward-looking sparks worth revisiting later — business or market "
            "opportunities, product/venture concepts, experiments to try, provocative \"what if\" questions, "
            "go-to-market or recruiting tactics, tooling ideas, and reusable principles. Include BOTH ideas "
            "explicitly raised in the conversation AND fresh ones that emerge from its context. Lines the "
            "note-taker already tagged with \"#IDEA\" are exactly this kind of spark — always carry those "
            "forward (but drop the literal \"#IDEA\" tag from the text). Write the way the note-taker does: "
            "terse, concrete, ~6-15 words, plain conversational English. A sentence fragment or a bare "
            "question is good. NO preamble verbs like \"Leverage/Utilize/Implement\", no buzzwords, no "
            "phrases-in-quotes, no two-clause explanations. An explicitly raised forward-looking idea remains "
            "an idea; 'not a recap' means do not restate facts, decisions, completed work, or assigned to-dos.\n\n"
        ),
        skip_if=_transcript_skip,
        fields=[
            FieldDef(
                name="summary",
                description=(
                    "3-8 who-said-what summaries of the highest-value items, one sentence each. Preserve concrete "
                    "numbers, named mechanisms, decisions, contrasts, and non-obvious specifics when they carry the "
                    "point. Prefer a specific claim over generic 'the group discussed X' topic-list bullets. Cover "
                    "important late-transcript developments, not just the opening. When the conversation reaches an "
                    "assessment, verdict, recommendation, or decision — a hiring call, go/no-go, or chosen option — "
                    "state it explicitly, including when it appears only in notes rather than dialogue. Never let "
                    "specificity about what participants said crowd out what was concluded."
                ),
                pydantic_type=list[str],
                to_yaml=list,
            ),
            FieldDef(
                name="keywords",
                description=(
                    "5-15 distinctive retrieval handles. Prioritize organizations/clients, products/tools, acronyms, "
                    "named methods or mechanisms, datasets/artifacts, and unusually specific concepts actually present. "
                    "Prefer terms someone might remember and search months later; replace generic categories with more "
                    "specific terms when possible. Speaker names are already captured in 'people', so include a speaker "
                    "name only when it is itself a useful retrieval handle; include other named people when relevant."
                ),
                pydantic_type=list[str],
                to_yaml=flow_list,
            ),
            FieldDef(
                name="people",
                description="Clearly identified speaker names only. Empty list if none.",
                pydantic_type=list[str],
                to_yaml=flow_list,
                extract=extract_speakers,  # try regex first; falls back to AI if empty
                clean=clean_people,        # filter placeholder names from AI output
            ),
            FieldDef(
                name="actions",
                description=(
                    "ALL agreed or clearly assigned actions, including minor or secondary commitments and handoffs. "
                    "Silently scan the entire transcript for every candidate commitment, not just the most salient ones. "
                    "For each candidate verify that someone accepted it or was explicitly assigned it; verify the owner "
                    "and direction/recipient when stated; verify it was not completed during the call unless follow-up "
                    "remains; and verify later evidence did not supersede or cancel it. Do not infer an owner merely from "
                    "who asked a question, gave advice, or spoke nearby. Then build a final commitment ledger: for each "
                    "owner and outcome, keep only the latest accepted instruction. "
                    "A later explicit direction overrides an earlier one, especially phrases such as 'instead' or "
                    "'no choice but', or a changed model, approach, or plan. Merge due date, artifact, recipient or "
                    "handoff, channel, escalation, and completion condition only when stated. Preserve explicit scope "
                    "such as both, each, all, and same. Drop completed-during-call work unless follow-up remains, "
                    "unaccepted suggestions, optional or conditional plans, exploratory ideas, duplicates, and "
                    "superseded actions. Also exclude asks made during the call that were never verbally accepted, "
                    "items already resolved before the call ended, and hedged personal intentions ('I should/might/could') "
                    "that were not assigned or explicitly offered as a follow-up to someone present. Format each as "
                    "'Owner: By D Mon YYYY. Specific observable action or "
                    "handoff.' Omit the date and any other unsupported detail. Resolve relative dates from the meeting "
                    "date, never the script run date. Empty list if none."
                ),
                pydantic_type=list[str],
                to_yaml=list,
            ),
            FieldDef(
                name="what-i-missed",
                description=(
                    "List the highest-leverage moments where I (Anand) missed or under-reacted to a “bid” "
                    "(request, concern, constraint, opportunity, or emotional signal) from others. "
                    "Read between the lines, but keep every item anchored to transcript evidence. Mentally list candidates "
                    "and pick only the highest-leverage ones. For each moment, concisely include (a) the exact quote, "
                    "fragment, or close paraphrase of what they said and (b) the follow-up question or move I _should_ "
                    "have made in the moment. Do not invent a psychological explanation for why I missed it. Only if a "
                    "situational reason is directly supported by the transcript (for example an interruption or explicit "
                    "time pressure), you may add it as a tentative 'Possible reason'. If anyone other than me speaks "
                    "substantively — asks questions, raises concerns or constraints, makes requests, or pushes back — "
                    "return at least 2 evidence-grounded items when such bids exist. Reserve an empty list for transcripts "
                    "with essentially no meaningful bids. Talks, workshops, and demos where I am the main speaker still "
                    "require scanning the Q&A and any explicit admissions of gaps or uncertainty for missed follow-ups. "
                    "Never invent filler merely to meet the count."
                ),
                pydantic_type=list[str],
                to_yaml=list,
                clean=clean_what_i_missed,
            ),
            FieldDef(
                name="ideas",
                description=(
                    "3-10 forward-looking sparks worth revisiting — opportunities, product/venture concepts, "
                    "experiments to try, provocative \"what if\" questions, go-to-market/recruiting tactics, "
                    "tooling ideas, or reusable principles. Capture BOTH forward-looking ideas explicitly raised (including any "
                    "lines tagged \"#IDEA\", but omit that literal tag) AND fresh ones that emerge from the "
                    "discussion. An explicitly raised forward-looking idea is valid even though it appears in the transcript: "
                    "'not a recap' means do not restate facts, decisions, completed work, or assigned actions as ideas. "
                    "A capability, feature, or practice that already exists and was merely described is not an idea, even "
                    "when phrased forward-lookingly. Fresh ideas must be directly grounded in the discussion; prefer "
                    "portable, testable, or surprising "
                    "sparks over generic advice. Each a terse, concrete one-liner of ~6-15 words in plain conversational "
                    "English; a fragment or bare question is fine. No \"Leverage/Utilize/Implement\" preambles, "
                    "buzzwords, or quoted phrases. Empty list if none."
                ),
                pydantic_type=list[str],
                to_yaml=list,
                clean=clean_ideas,
            ),
        ],
    ),
    ContentSet(
        name="blog",
        base_dir=Path("/home/sanand/code/blog"),
        prompt="",
        prompt_builder=blog_prompt,
        fields=[
            FieldDef(
                name="description",
                description=(
                    "20-40 word human-first description. Use first person when natural. Normal posts: at most 2 "
                    "supporting specifics; roundups: at most 4. Concept/opinion: thesis plus at most one example, never "
                    "compress a source list. Contrast/ranking: preserve the baseline and standout result. Story/puzzle: include both "
                    "the concrete action and what it lets someone conclude or prove, not merely the moral."
                ),
                pydantic_type=str,
                to_yaml=str,
            ),
            FieldDef(
                name="tags",
                description=(
                    "2-4 canonical tags for useful human navigation and machine clustering. Capture the organizing "
                    "question/lens first, then only substantial independent facets; avoid settings, examples, generic "
                    "parents, synonyms, and near-duplicates."
                ),
                pydantic_type=list[str],
                to_yaml=flow_list,
                clean=clean_blog_tags,
            ),
        ],
        default_globs=["posts/**/*.md", "pages/**/*.md"],
        exclude_names=["SKILL.md"],
        meta_position="after",
        default_workers=8,
    ),
]

CONTENT_SET_MAP: dict[str, ContentSet] = {cs.name: cs for cs in CONTENT_SETS}


# ── Token/cost tracking ───────────────────────────────────────────────────────

@dataclass
class Usage:
    prompt: int = 0
    output: int = 0
    calls: int = 0

    def add(self, prompt: int, output: int) -> None:
        self.prompt += prompt
        self.output += output
        self.calls += 1

    def cost(self, model: str) -> float:
        p_in, p_out = PRICING.get(model, DEFAULT_PRICING)
        return self.prompt / 1e6 * p_in + self.output / 1e6 * p_out

    def as_dict(self) -> dict:
        return {"prompt": self.prompt, "output": self.output, "calls": self.calls}


# ── AI call ───────────────────────────────────────────────────────────────────

def response_model(fields: list[FieldDef]):
    return create_model(
        "ResponseModel",
        **{f.name: (f.pydantic_type, PydanticField(description=f.description))
           for f in fields},
    )


def ai_input(content_set: ContentSet, text: str, fields: list[FieldDef]) -> str:
    return (
        content_set.prompt_for(text, fields)
        + without_frontmatter_fields(text, {field.name for field in fields})
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def call_gemini(client, model: str, content_set: ContentSet, text: str, fields: list[FieldDef]):
    from google.genai import types

    ResponseModel = response_model(fields)
    response = client.models.generate_content(
        model=model,
        contents=ai_input(content_set, text, fields),
        config=types.GenerateContentConfig(
            temperature=0,
            # Pin the API default used by this benchmark for reproducibility.
            thinking_config=types.ThinkingConfig(thinking_level="medium"),
            response_mime_type="application/json",
            response_json_schema=ResponseModel.model_json_schema(),
        ),
    )
    if response.text is None:
        reason = str(response.candidates[0].finish_reason) if response.candidates else "unknown"
        raise ValueError(f"Gemini returned no text (finish_reason={reason})")

    meta = ResponseModel.model_validate_json(response.text)
    usage = Usage()
    if response.usage_metadata:
        usage.add(
            response.usage_metadata.prompt_token_count or 0,
            (response.usage_metadata.candidates_token_count or 0)
            + (response.usage_metadata.thoughts_token_count or 0),
        )
    return meta, usage


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def call_openai(client, model: str, content_set: ContentSet, text: str, fields: list[FieldDef]):
    ResponseModel = response_model(fields)
    response = client.responses.parse(
        model=model,
        input=ai_input(content_set, text, fields),
        text_format=ResponseModel,
        # This was the GPT-5.6 default during the benchmark; pin it for reruns.
        reasoning={"effort": "medium"},
        store=False,
    )
    if not response.output_parsed:
        raise ValueError("OpenAI returned no parsed output")

    usage = Usage()
    if response.usage:
        usage.add(response.usage.input_tokens or 0, response.usage.output_tokens or 0)
    return response.output_parsed, usage


def call_chatgpt(client, model: str, content_set: ContentSet, text: str, fields: list[FieldDef]):
    with client.responses.stream(
        model=model,
        input=[{"role": "user", "content": ai_input(content_set, text, fields)}],
        text_format=response_model(fields),
        store=False,
    ) as stream:
        for event in stream:
            if event.type == "response.completed":
                response = event.response
                break
            if event.type in {"response.failed", "response.incomplete"}:
                details = event.response.error or event.response.incomplete_details
                raise ChatGPTError(f"ChatGPT {event.type}: {details}")
            if event.type == "error":
                raise ChatGPTError(f"ChatGPT {event.code}: {event.message}")
        else:
            raise ChatGPTError("ChatGPT stream ended before response.completed.")
    if not response.output_parsed:
        raise ChatGPTError("ChatGPT returned no parsed output.")
    usage = Usage()
    if response.usage:
        usage.add(response.usage.input_tokens or 0, response.usage.output_tokens or 0)
    return response.output_parsed, usage


def call_ai(provider: str, client, model: str, content_set: ContentSet, text: str, fields: list[FieldDef]):
    if provider == "gemini":
        return call_gemini(client, model, content_set, text, fields)
    if provider == "openai":
        return call_openai(client, model, content_set, text, fields)
    if provider == "chatgpt":
        return call_chatgpt(client, model, content_set, text, fields)
    raise ValueError(f"Unknown provider: {provider}")


# ── Per-file processing ───────────────────────────────────────────────────────

def process_file(
    path: Path, provider: str, client, model: str, dry_run: bool, force: bool, content_set: ContentSet,
    selected_fields: set[str] | None = None,
) -> dict:
    result: dict = {
        "file": str(path),
        "name": path.name,
        "status": "skipped",
        "added_fields": [],
        "skipped_reason": None,
        "tokens": {"prompt": 0, "output": 0},
        "cost_usd": None if provider == "chatgpt" else 0.0,
        "proposals": [],
    }

    text = path.read_text(encoding="utf-8")
    metadata, body, had_fm = parse_frontmatter(text)
    meta_keys = content_set.meta_keys

    eligible_keys = [k for k in meta_keys if selected_fields is None or k in selected_fields]
    missing = [k for k in eligible_keys if force or is_unprocessed(metadata.get(k))]
    if not missing:
        result["skipped_reason"] = "all fields present"
        return result

    if count_content_lines(text) < MIN_CONTENT_LINES:
        result["skipped_reason"] = "trivial content"
        return result

    if content_set.skip_if and (reason := content_set.skip_if(body)):
        result["skipped_reason"] = reason
        return result

    updates: dict = {}

    # Pre-extraction: try regex (no API call)
    for fdef in content_set.fields:
        if fdef.name not in missing or fdef.extract is None:
            continue
        if extracted := fdef.extract(body):
            updates[fdef.name] = fdef.to_yaml(extracted)
            result["added_fields"].append(fdef.name)
            missing.remove(fdef.name)

    # AI for remaining missing fields
    if missing:
        try:
            missing_fields = [fdef for fdef in content_set.fields if fdef.name in missing]
            # Blog descriptions are human-facing prose while tags need taxonomy-heavy context.
            # Generate them separately so tag candidates do not leak into the visible description.
            field_groups = [[fdef] for fdef in missing_fields] if content_set.name == "blog" else [missing_fields]
            usage = Usage()
            for field_group in field_groups:
                ai, field_usage = call_ai(provider, client, model, content_set, text, field_group)
                usage.prompt += field_usage.prompt
                usage.output += field_usage.output
                usage.calls += field_usage.calls
                for fdef in field_group:
                    val = getattr(ai, fdef.name)
                    if content_set.name == "blog" and fdef.name == "tags":
                        val, result["proposals"] = split_blog_tags(val)
                    elif fdef.clean is not None:
                        val = fdef.clean(val)
                    # Always write, even [] — marks field as processed so we don't re-run
                    updates[fdef.name] = fdef.to_yaml(val)
                    result["added_fields"].append(fdef.name)
            result["tokens"] = usage.as_dict()
            if provider != "chatgpt":
                result["cost_usd"] = round(usage.cost(model), 6)
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e.__cause__ or e)
            return result

    full_meta = reorder_metadata(metadata, updates, meta_keys, content_set.meta_position) if force else None
    if not dry_run:
        write_file(path, had_fm, text, updates, content_set.meta_position, full_metadata=full_meta)
        if content_set.name == "blog":
            result["source"] = blog_source_path(path, content_set.base_dir)
            result["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result["status"] = "dry-run" if dry_run else "updated"
    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

@app.command(epilog="Over SSH, use 'summarize.py login chatgpt --paste' to sign in on another device.")
def main(
    content_set_name: str             = typer.Argument(..., help=f"Content set: {', '.join(CONTENT_SET_MAP)}, or login chatgpt"),
    patterns:  list[str] | None    = typer.Argument(None, help="Glob patterns; relative resolved from ., absolute start with /"),
    model:     str | None             = typer.Option(None, help="Model ID; defaults by provider"),
    provider:  str                    = typer.Option("openai", help="Provider: gemini|openai|chatgpt"),
    workers:   int | None             = typer.Option(None, "--workers", help="Parallel API workers; defaults by content set"),
    dry_run:   bool                   = typer.Option(False, "--dry-run",   help="Show changes without writing"),
    force:     bool                   = typer.Option(False, "--force",    help="Re-process all fields via API"),
    fmt:       str                    = typer.Option("auto", "--format",   help="Output: text|json|auto"),
    verbose:   bool                   = typer.Option(False, "--verbose", "-v", help="Show skipped files"),
    fields:    str | None          = typer.Option(None, "--fields", help="Comma-separated fields to process"),
    account:   str | None             = typer.Option(None, "--account", help="Saved ChatGPT account label from --accounts"),
    paste:     bool                   = typer.Option(False, "--paste", help="Login: paste the callback URL from a remote browser"),
    new:       bool                   = typer.Option(False, "--new-account", help="Login: register an additional ChatGPT account or workspace"),
    accounts:  bool                   = typer.Option(False, "--accounts", help="Login: list saved ChatGPT accounts"),
) -> None:
    """Add AI-generated metadata to content files (transcripts, blog posts, etc.)."""
    if content_set_name == "login":
        if patterns != ["chatgpt"]:
            raise typer.BadParameter(f"Use {CHATGPT_LOGIN}.")
        try:
            login_chatgpt(account, paste, new, accounts)
        except (ChatGPTError, OSError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from None
        return

    if paste or new or accounts:
        raise typer.BadParameter(f"Use --paste, --new-account, or --accounts with {CHATGPT_LOGIN}.")
    if account and provider != "chatgpt":
        raise typer.BadParameter("Use --account with --provider chatgpt.")

    if content_set_name not in CONTENT_SET_MAP:
        valid = ", ".join(CONTENT_SET_MAP)
        console.print(f"[red]Unknown content set '{content_set_name}'. Valid: {valid}[/red]")
        raise typer.Exit(1)

    content_set = CONTENT_SET_MAP[content_set_name]
    workers = workers or content_set.default_workers
    selected_fields = None
    if fields:
        requested = {name.strip() for name in fields.split(",") if name.strip()}
        unknown = requested - set(content_set.meta_keys)
        if unknown:
            console.print(f"[red]Unknown fields: {', '.join(sorted(unknown))}[/red]")
            raise typer.Exit(1)
        selected_fields = requested

    if provider not in DEFAULT_MODELS:
        console.print(f"[red]Unknown provider '{provider}'. Valid: {', '.join(DEFAULT_MODELS)}[/red]")
        raise typer.Exit(1)
    model = model or DEFAULT_MODELS[provider]

    if provider != "chatgpt":
        env_path = Path.home() / "code/scripts/.env"
        load_dotenv(env_path)
        key_name = "GEMINI_API_KEY" if provider == "gemini" else "OPENAI_API_KEY"
        # A non-empty process value wins even if the runtime predefines the variable as empty.
        api_key = os.environ.get(key_name) or dotenv_values(env_path).get(key_name)
        if not api_key:
            console.print(f"[red]{key_name} not found in environment or .env[/red]")
            raise typer.Exit(1)

    quiet = os.environ.get("DAILY_ACTIVITIES_QUIET") == "1"
    use_json = fmt == "json" or (fmt == "auto" and not quiet and not sys.stdout.isatty())
    files = resolve_files(patterns or [], content_set)
    if not files:
        msg = f"No files matched: {patterns}"
        print(json.dumps({"error": msg}) if use_json else msg)
        raise typer.Exit(1)

    if provider == "gemini":
        from google import genai
        client = genai.Client(api_key=api_key)
    else:
        from openai import OpenAI
        if provider == "chatgpt":
            try:
                session = chatgpt_record(account)
            except ChatGPTError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(1) from None
            client = OpenAI(api_key=lambda: chatgpt_access_token(session), base_url=CHATGPT_RESOURCE,
                            organization="", project="", max_retries=0)
        else:
            client = OpenAI(api_key=api_key)

    results: list[dict] = []
    total_usage = Usage()

    def on_done(result: dict) -> None:
        results.append(result)
        t = result.get("tokens", {})
        total_usage.prompt += t.get("prompt", 0)
        total_usage.output += t.get("output", 0)
        total_usage.calls += t.get("calls", 0)
        with _print_lock:
            if use_json:
                print(json.dumps(result), flush=True)
            else:
                status = result["status"]
                name = result["name"]
                if status == "skipped":
                    if verbose:
                        console.print(f"[dim]SKIP {name}: {result['skipped_reason']}[/dim]")
                elif status == "error":
                    console.print(f"[red]ERROR {name}: {result.get('error')}[/red]")
                else:
                    tag = "[yellow]DRY-RUN[/yellow]" if dry_run else "[green]UPDATED[/green]"
                    added = result["added_fields"]
                    tok = result["tokens"]
                    cost = "ChatGPT plan" if provider == "chatgpt" else f"${result['cost_usd']:.4f}"
                    console.print(
                        f"{tag} {name} +{added} | "
                        f"[dim]{tok['prompt']}in/{tok['output']}out tok {cost}[/dim]"
                    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                process_file, path, provider, client, model, dry_run, force, content_set, selected_fields
            ): path
            for path in files
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                on_done(future.result())
            except Exception as e:
                path = futures[future]
                on_done({
                    "file": str(path), "name": path.name, "status": "error",
                    "added_fields": [], "skipped_reason": None,
                    "tokens": {"prompt": 0, "output": 0}, "cost_usd": None if provider == "chatgpt" else 0.0,
                    "error": str(e),
                })

    if content_set.name == "blog" and not dry_run:
        evidence = [
            result for result in results
            if result["status"] == "updated" and "content_hash" in result
        ]
        if evidence:
            merge_blog_tag_proposals(BLOG_PROPOSALS_PATH, evidence)

    if not use_json:
        n_updated = sum(1 for r in results if r["status"] in ("updated", "dry-run"))
        n_skipped = sum(1 for r in results if r["status"] == "skipped")
        n_errors  = sum(1 for r in results if r["status"] == "error")
        console.print(
            f"\n[bold]Done:[/bold] {n_updated} updated, {n_skipped} skipped, {n_errors} errors"
        )
        pricing = PRICING.get(model, DEFAULT_PRICING)
        cost = "ChatGPT plan" if provider == "chatgpt" else (
            f"[bold]Cost:[/bold] ${total_usage.cost(model):.4f} "
            f"[dim](${pricing[0]}/1M in, ${pricing[1]}/1M out)[/dim]"
        )
        console.print(
            f"[bold]Tokens:[/bold] {total_usage.prompt:,} in + {total_usage.output:,} out"
            f" ({total_usage.calls} calls) | {cost}"
        )

    raise typer.Exit(1 if any(r["status"] == "error" for r in results) else 0)


def resolve_files(patterns: list[str], content_set: ContentSet) -> list[Path]:
    """Resolve file patterns to a sorted, deduplicated list of paths.

    - No patterns → expand content_set.default_globs against content_set.base_dir
    - Relative pattern (no leading /) → expand against current directory (.)
    - Absolute pattern (starts with /) → use as-is
    """
    if not patterns:
        files: list[Path] = []
        for g in content_set.default_globs:
            files.extend(Path(p) for p in glob_module.glob(
                str(content_set.base_dir / g), recursive=True
            ))
    else:
        files = []
        for pattern in patterns:
            root = pattern if pattern.startswith("/") else str(Path(".") / pattern)
            files.extend(Path(f) for f in glob_module.glob(root, recursive=True))

    if content_set.exclude_names:
        excluded = set(content_set.exclude_names)
        files = [f for f in files if f.name not in excluded]
    return sorted(set(files), reverse=True)


if __name__ == "__main__":
    app()
