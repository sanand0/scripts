#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-frontmatter>=1.0.0",
#     "markdown-it-py>=3.0.0",
#     "premailer>=3.10.0",
#     "pygments>=2.17.0",
#     "typer>=0.12.0",
#     "platformdirs>=4.0.0",
#     "google-auth>=2.0.0",
#     "google-auth-oauthlib>=1.0.0",
#     "google-auth-httplib2>=0.2.0",
#     "google-api-python-client>=2.0.0",
# ]
# ///
"""Convert markdown posts to email-friendly HTML and optionally send via Gmail."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import frontmatter
import typer
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from markdown_it import MarkdownIt
from platformdirs import user_config_path
from premailer import transform
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

APP_NAME = "htmlemail"
CONFIG_FILE = "config.json"
CLIENT_SECRETS_FILE = "credentials.json"
TOKENS_DIR = "tokens"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Keep Gmail permissions minimal. OpenID Connect scopes let us verify which
# Google account authenticated without asking for Gmail read access.
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.send",
]

# Google returns these canonical scope names for the OIDC short scopes. They
# are equivalent for our use, but oauthlib compares strings literally.
GOOGLE_SCOPE_ALIASES = {
    "email": "https://www.googleapis.com/auth/userinfo.email",
    "profile": "https://www.googleapis.com/auth/userinfo.profile",
}

ATTR_URL_RE = re.compile(
    r"\b(?P<attr>href|src)\s*=\s*(?P<quote>[\"']?)(?P<url>[^\"'\s>]+)(?P=quote)",
    flags=re.IGNORECASE,
)


class HtmlemailError(Exception):
    """User-facing error for CLI failures."""


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    base_url: str | None
    warnings: list[str]


@dataclass(frozen=True)
class SenderProfile:
    requested_email: str
    verified_email: str
    display_name: str
    token_path: Path
    identity: dict[str, Any]


def eprint(message: str) -> None:
    """Print a progress or warning message without contaminating HTML stdout."""
    typer.echo(message, err=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalized_email(email: str) -> str:
    return email.strip().lower()


def scopes_fingerprint(scopes: list[str] = SCOPES) -> str:
    return hashlib.sha256("\n".join(sorted(scopes)).encode()).hexdigest()[:16]


def split_scopes(scopes: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if not scopes:
        return []
    if isinstance(scopes, str):
        return scopes.split()
    return list(scopes)


def canonical_scope(scope: str) -> str:
    return GOOGLE_SCOPE_ALIASES.get(scope, scope)


def canonical_scope_set(scopes: str | list[str] | tuple[str, ...] | None) -> set[str]:
    return {canonical_scope(scope) for scope in split_scopes(scopes)}


def validate_granted_scopes(creds: Credentials) -> None:
    """Ensure Google granted the scopes we need, accepting known aliases."""
    granted = canonical_scope_set(getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None))
    required = canonical_scope_set(SCOPES)
    missing = sorted(required - granted)
    if missing:
        raise HtmlemailError(
            "Google did not grant the required OAuth scopes: "
            f"{', '.join(missing)}. Re-run with --reauth and approve all requested permissions."
        )


def run_oauth_flow(credentials_path: Path) -> Credentials:
    """Run desktop OAuth while tolerating Google's equivalent scope aliases."""
    old_relax_scope = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        return flow.run_local_server(port=0)
    finally:
        if old_relax_scope is None:
            os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
        else:
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = old_relax_scope


def get_config_dir(create: bool = True) -> Path:
    """Return the platform-appropriate configuration directory.

    Tests and automation can override this with HTMLEMAIL_CONFIG_DIR.
    """
    override = os.environ.get("HTMLEMAIL_CONFIG_DIR")
    path = Path(override).expanduser() if override else user_config_path(APP_NAME, ensure_exists=False)
    if create:
        path.mkdir(parents=True, exist_ok=True)
        (path / TOKENS_DIR).mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE


def get_client_secrets_path() -> Path:
    return get_config_dir() / CLIENT_SECRETS_FILE


def default_config() -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "version": 1,
        "created_at": now_iso(),
        "profiles": {},
    }


def load_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return default_config()
    try:
        config = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise HtmlemailError(f"Invalid config file: {path}: {exc}") from exc
    config.setdefault("app", APP_NAME)
    config.setdefault("version", 1)
    config.setdefault("profiles", {})
    return config


def save_config(config: dict[str, Any]) -> None:
    path = get_config_path()
    config.setdefault("updated_at", now_iso())
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    tmp_path.replace(path)


def token_filename_for_email(email: str) -> str:
    """Return a portable, non-secret token filename for an email address."""
    normalized = normalized_email(email)
    slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "sender"
    suffix = hashlib.sha256(normalized.encode()).hexdigest()[:8]
    return f"{slug}-{suffix}.json"


def get_default_token_path(email: str) -> Path:
    return get_config_dir() / TOKENS_DIR / token_filename_for_email(email)


def config_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(get_config_dir().resolve()))
    except ValueError:
        return str(path.expanduser())


def resolve_profile_token_path(profile: dict[str, Any], email: str) -> Path:
    token_path = profile.get("token_path")
    if token_path:
        path = Path(token_path).expanduser()
        if not path.is_absolute():
            path = get_config_dir() / path
        return path
    return get_default_token_path(email)


def init_config(client_secrets: Path) -> Path:
    if not client_secrets.exists():
        raise HtmlemailError(f"Client secrets file not found: {client_secrets}")
    target = get_client_secrets_path()
    shutil.copy2(client_secrets, target)
    config = load_config()
    config["client_secrets_path"] = config_relative_path(target)
    config.setdefault("initialized_at", now_iso())
    save_config(config)
    return target


def show_config() -> None:
    config_dir = get_config_dir()
    config = load_config()
    typer.echo(f"Config dir: {config_dir}")
    typer.echo(f"Config file: {get_config_path()}")
    typer.echo(f"Client secrets: {get_client_secrets_path()}")
    typer.echo(f"Tokens dir: {config_dir / TOKENS_DIR}")
    profiles = config.get("profiles", {})
    if not profiles:
        typer.echo("Profiles: none")
        return
    typer.echo("Profiles:")
    for key, profile in sorted(profiles.items()):
        token_path = resolve_profile_token_path(profile, key)
        verified = profile.get("verified_email", key)
        name = profile.get("display_name") or verified
        updated = profile.get("updated_at", "unknown")
        typer.echo(f"- {verified} ({name})")
        typer.echo(f"  token: {token_path}")
        typer.echo(f"  updated: {updated}")


def logout_from(email: str) -> None:
    normalized = normalized_email(email)
    config = load_config()
    profile = config.get("profiles", {}).pop(normalized, None)
    token_path = resolve_profile_token_path(profile or {}, normalized)
    if token_path.exists():
        token_path.unlink()
    save_config(config)
    eprint(f"✓ Removed profile and token for {normalized}")


def is_relative_url(url: str) -> bool:
    if not url or url.startswith("#"):
        return False
    parsed = urlparse(url)
    return not parsed.scheme and not parsed.netloc


def rewrite_attr_urls(html: str, replacer) -> str:
    """Rewrite href/src attributes while preserving the original quote style."""

    def replace_match(match: re.Match[str]) -> str:
        attr = match.group("attr")
        quote = match.group("quote") or '"'
        url = match.group("url")
        return f"{attr}={quote}{replacer(url)}{quote}"

    return ATTR_URL_RE.sub(replace_match, html)


def find_relative_urls(html: str) -> list[str]:
    return sorted({match.group("url") for match in ATTR_URL_RE.finditer(html) if is_relative_url(match.group("url"))})


def resolve_links(html: str, base_url: str) -> str:
    """Resolve relative href/src attributes to full URLs using base_url."""

    def resolve(url: str) -> str:
        return urljoin(base_url, url) if is_relative_url(url) else url

    return rewrite_attr_urls(html, resolve)


def replace_youtube_embeds(html: str) -> str:
    """Replace YouTube iframe embeds with clickable thumbnail images."""
    youtube_pattern = r'<iframe[^>]*src="(?:https?:)?//(?:www\.)?youtube\.com/embed/([^"?]+)[^"]*"[^>]*>.*?</iframe>'

    def replace_iframe(match: re.Match[str]) -> str:
        video_id = match.group(1)
        return (
            f'<a href="https://youtu.be/{video_id}">'
            f'<img src="https://i.ytimg.com/vi_webp/{video_id}/sddefault.webp" '
            f'alt="YouTube video" style="max-width: 100%; height: auto;">'
            f"</a>"
        )

    return re.sub(youtube_pattern, replace_iframe, html, flags=re.IGNORECASE | re.DOTALL)


def get_html_attr(tag: str, attr: str) -> str | None:
    """Extract an HTML attribute value from a tag fragment."""
    match = re.search(
        rf"\b{re.escape(attr)}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))",
        tag,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1) or match.group(2) or match.group(3)
    return None


def replace_media_embeds(html: str) -> str:
    """Replace video/audio tags with email-friendly fallback links."""

    def first_source(open_tag: str, inner_html: str) -> str | None:
        if src := get_html_attr(open_tag, "src"):
            return src
        for source_tag in re.findall(r"<source\b[^>]*>", inner_html, flags=re.IGNORECASE):
            if src := get_html_attr(source_tag, "src"):
                return src
        return None

    def replace_match(match: re.Match[str]) -> str:
        media_kind = match.group(1).lower()
        open_tag = match.group(2)
        inner_html = match.group(3)

        source = first_source(open_tag, inner_html)
        title = media_kind.capitalize()
        action = "Watch video" if media_kind == "video" else "Listen to audio"
        parts = (
            [f'<p><strong>{title}:</strong> <a href="{source}">{action}</a></p>']
            if source
            else [f"<p><strong>{title}:</strong> Media unavailable in email</p>"]
        )

        caption_links: list[str] = []
        for track_tag in re.findall(r"<track\b[^>]*>", inner_html, flags=re.IGNORECASE):
            kind = (get_html_attr(track_tag, "kind") or "").lower()
            if kind and kind not in {"captions", "subtitles"}:
                continue
            if track_src := get_html_attr(track_tag, "src"):
                caption_links.append(f'<a href="{track_src}">Open captions</a>')

        if caption_links:
            parts.append(f"<p><strong>Captions:</strong> {', '.join(caption_links)}</p>")
        return "".join(parts)

    return re.sub(
        r"<(video|audio)\b([^>]*)>(.*?)</\1>",
        replace_match,
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def frontmatter_base_url(post: frontmatter.Post) -> str | None:
    for key in ("base_url", "canonical_url", "url"):
        value = post.get(key)
        if value:
            return str(value)
    return None


def render_email(markdown_file: Path, base_url: str | None = None) -> RenderedEmail:
    """Convert a markdown file to email-friendly HTML."""
    post = frontmatter.load(markdown_file)
    content = re.sub(r"\\[ \t]*(\r?\n)", r"\1", post.content)

    def highlight_code(code: str, lang: str | None, _attrs: str) -> str | None:
        if not lang:
            return None
        try:
            lexer = get_lexer_by_name(lang)
        except ClassNotFound:
            return None
        formatter = HtmlFormatter(style="default", nowrap=True)
        return pygments_highlight(code, lexer, formatter)

    md = (
        MarkdownIt(
            "commonmark",
            {
                "html": True,
                "breaks": True,
                "highlight": highlight_code,
            },
        )
        .enable("table")
        .enable("strikethrough")
    )
    html_content = md.render(content)
    html_content = replace_youtube_embeds(html_content)
    html_content = replace_media_embeds(html_content)

    resolved_base_url = base_url or frontmatter_base_url(post)
    warnings: list[str] = []
    if resolved_base_url:
        html_content = resolve_links(html_content, resolved_base_url)
    else:
        relative_urls = find_relative_urls(html_content)
        if relative_urls:
            preview = ", ".join(relative_urls[:5])
            more = f" and {len(relative_urls) - 5} more" if len(relative_urls) > 5 else ""
            warnings.append(
                "Relative href/src URLs were left unchanged because no --base-url "
                f"or frontmatter base_url/canonical_url/url was provided: {preview}{more}"
            )

    formatter = HtmlFormatter(style="default")
    pygments_css = formatter.get_style_defs("pre code")
    subject = post.get("title", "Blog Post")

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                line-height: 1.6;
                max-width: 600px;
                background-color: #ffffff;
            }}
            h1, h2, h3, h4, h5, h6 {{
                margin-top: 1.5em;
                margin-bottom: 0.5em;
                font-weight: 600;
            }}
            h1 {{ font-size: 2em; }}
            h2 {{ font-size: 1.5em; }}
            h3 {{ font-size: 1.25em; }}
            p {{ margin-bottom: 1em; }}
            a {{ color: #0366d6; text-decoration: underline; }}
            img {{ max-width: 100%; height: auto; margin: 1em 0; }}
            code {{
                padding: 0.2em 0.4em;
                font-size: 90%;
                background-color: #f5f5f5;
                border-radius: 3px;
                font-family: ui-monospace, 'Cascadia Code', 'Source Code Pro', Menlo, Consolas, 'DejaVu Sans Mono', monospace;
            }}
            pre {{
                padding: 1em;
                overflow: auto;
                background-color: #f5f5f5;
                border-radius: 3px;
                margin: 1em 0;
            }}
            pre code {{
                padding: 0;
                background-color: transparent;
            }}
            /* Pygments syntax highlighting styles */
            {pygments_css}
            table {{
                border-collapse: collapse;
                margin: 1em 0;
            }}
            table th, table td {{
                padding: 8px 12px;
                border: 1px solid #ddd;
                text-align: left;
            }}
            table th {{
                font-weight: 600;
                background-color: #f5f5f5;
            }}
            blockquote {{
                padding-left: 1em;
                color: #666;
                border-left: 3px solid #ddd;
                margin: 1em 0;
            }}
            hr {{
                border: 0;
                border-top: 1px solid #ddd;
                margin: 2em 0;
            }}
            ul, ol {{ padding-left: 2em; margin: 1em 0; }}
            li {{ margin-bottom: 0.5em; }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

    email_html = transform(html_template)
    return RenderedEmail(subject=str(subject), html=email_html, base_url=resolved_base_url, warnings=warnings)


def markdown_to_email_html(markdown_file: Path, base_url: str | None = None) -> tuple[str, str]:
    """Backward-compatible wrapper returning only subject and HTML."""
    rendered = render_email(markdown_file, base_url)
    return rendered.subject, rendered.html


def decode_jwt_payload(token: str) -> dict[str, Any]:
    """Decode an ID-token payload without verification for local metadata fallback only."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}


def identity_from_credentials(creds: Credentials) -> dict[str, Any]:
    """Return OIDC identity claims for the authenticated Google account."""
    session = AuthorizedSession(creds)
    try:
        response = session.get(USERINFO_URL, timeout=10)
        if response.ok:
            return response.json()
    except Exception:
        pass

    id_token = getattr(creds, "id_token", None)
    if id_token:
        identity = decode_jwt_payload(id_token)
        if identity:
            return identity
    raise HtmlemailError("Could not verify the authenticated Google identity. Try re-running with --reauth.")


def validate_sender_identity(requested_email: str, identity: dict[str, Any]) -> None:
    actual_email = normalized_email(str(identity.get("email", "")))
    requested = normalized_email(requested_email)
    if not actual_email:
        raise HtmlemailError("Google did not return an email identity for this token. Try re-running with --reauth.")
    if actual_email != requested:
        raise HtmlemailError(
            f"Authenticated Google account is {actual_email}, but --from requested {requested}. "
            "Re-run with the matching --from value or use --reauth to create a new token."
        )


def get_credentials_for_sender(
    from_email: str,
    token_override: Path | None = None,
    reauth: bool = False,
) -> tuple[Credentials, SenderProfile]:
    """Load, refresh, or create OAuth credentials for a requested sender."""
    requested = normalized_email(from_email)
    config = load_config()
    profile = config.get("profiles", {}).get(requested, {})
    token_path = token_override.expanduser() if token_override else resolve_profile_token_path(profile, requested)
    credentials_path = get_client_secrets_path()

    if not credentials_path.exists():
        raise HtmlemailError(
            f"Google OAuth client secrets not found at {credentials_path}. "
            "Run: htmlemail.py --init --client-secrets /path/to/credentials.json"
        )

    expected_fingerprint = scopes_fingerprint()
    if profile.get("scopes_fingerprint") and profile.get("scopes_fingerprint") != expected_fingerprint:
        reauth = True

    creds: Credentials | None = None
    if token_path.exists() and not reauth:
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token and not reauth:
            creds.refresh(Request())
        else:
            creds = run_oauth_flow(credentials_path)

    validate_granted_scopes(creds)
    identity = identity_from_credentials(creds)
    validate_sender_identity(requested, identity)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json())

    verified_email = normalized_email(str(identity["email"]))
    display_name = str(identity.get("name") or identity.get("given_name") or verified_email)
    stored_profile = {
        "requested_email": requested,
        "verified_email": verified_email,
        "display_name": display_name,
        "google_sub": identity.get("sub"),
        "token_path": config_relative_path(token_path),
        "scopes_fingerprint": expected_fingerprint,
        "created_at": profile.get("created_at", now_iso()),
        "updated_at": now_iso(),
    }
    config.setdefault("profiles", {})[requested] = stored_profile
    save_config(config)

    return creds, SenderProfile(
        requested_email=requested,
        verified_email=verified_email,
        display_name=display_name,
        token_path=token_path,
        identity=identity,
    )


def format_recipients(recipients: list[str]) -> str:
    """Format recipients for email headers."""
    return ", ".join(recipients)


def send_email(
    gmail_service,
    sender: SenderProfile,
    to: list[str],
    subject: str,
    html_body: str,
    cc: list[str],
) -> None:
    """Send an HTML email via Gmail API using the authenticated sender profile."""
    message = MIMEMultipart("alternative")
    message["To"] = format_recipients(to)
    if cc:
        message["Cc"] = format_recipients(cc)
    message["From"] = formataddr((sender.display_name, sender.verified_email))
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    gmail_service.users().messages().send(userId="me", body={"raw": raw_message}).execute()


def run_tests() -> None:
    """Run minimal inline tests without requiring Google credentials."""
    import tempfile

    def render(md: str, *, fm: str = "title: Test", base_url: str | None = "https://example.com/blog/post/") -> tuple[str, str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "post.md"
            path.write_text(f"---\n{fm}\n---\n\n" + md)
            subject, html = markdown_to_email_html(path, base_url)
            return subject, html

    _subject, html = render("- A\n  - B\n")
    assert "<ul" in html and "<li" in html and "B" in html

    _subject, html = render("```python\nprint('hi')\n```\n")
    assert "print" in html and "<pre" in html and "<code" in html

    _subject, html = render("| A | B |\n| - | - |\n| 1 | 2 |\n")
    assert "<table" in html and "<th" in html and "<td" in html

    _subject, html = render('<div markdown="1">**bold**</div>')
    assert "<div" in html and "**bold**" in html

    _subject, html = render('<iframe src="https://www.youtube.com/embed/abc123"></iframe>')
    assert "youtu.be/abc123" in html and "i.ytimg.com" in html

    _subject, html = render(
        """
<video controls poster="../poster.webp" title="Demo walkthrough">
  <source src="../clip.webm" type="video/webm">
  <source src="../clip.mp4" type="video/mp4">
  <track kind="captions" src="../clip.en.vtt" srclang="en" label="English">
</video>
"""
    )
    assert "<video" not in html
    assert "<strong>Video:</strong>" in html and "Watch video" in html
    assert "https://example.com/blog/clip.webm" in html
    assert "<strong>Captions:</strong>" in html
    assert "https://example.com/blog/clip.en.vtt" in html

    _subject, html = render(
        """
<audio controls aria-label="Interview recording">
  <source src="../episode.ogg" type="audio/ogg">
  <source src="../episode.mp3" type="audio/mpeg">
  <track kind="subtitles" src="../episode.en.vtt" srclang="en">
</audio>
"""
    )
    assert "<audio" not in html
    assert "<strong>Audio:</strong>" in html and "Listen to audio" in html
    assert "https://example.com/blog/episode.ogg" in html
    assert "<strong>Captions:</strong>" in html
    assert "https://example.com/blog/episode.en.vtt" in html

    _subject, html = render("[rel](../x)\n\n![img](../i.png)\n")
    assert "https://example.com/blog/x" in html
    assert "https://example.com/blog/i.png" in html
    assert "s-anand.net" not in html

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "post.md"
        path.write_text("---\ntitle: Test\n---\n\n[rel](../x)\n\n![img](../i.png)\n")
        rendered = render_email(path, None)
        assert "../x" in rendered.html and "../i.png" in rendered.html
        assert rendered.warnings and "Relative href/src URLs" in rendered.warnings[0]
        assert "s-anand.net" not in rendered.html

    _subject, html = render(
        "[rel](../x)\n",
        fm="title: Test\nbase_url: https://frontmatter.example/blog/post/",
        base_url=None,
    )
    assert "https://frontmatter.example/blog/x" in html

    _subject, html = render("Line 1\\\nLine 2\n")
    assert "Line 1" in html and "Line 2" in html and "<br" in html

    assert format_recipients(["a@example.com", "b@example.com"]) == "a@example.com, b@example.com"
    token_name = token_filename_for_email("A.B+X@Gmail.COM")
    assert token_name.startswith("a_b_x_gmail_com-") and token_name.endswith(".json")
    assert canonical_scope_set(SCOPES) == canonical_scope_set(
        "openid https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/gmail.send"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        old_config_dir = os.environ.get("HTMLEMAIL_CONFIG_DIR")
        os.environ["HTMLEMAIL_CONFIG_DIR"] = tmpdir
        try:
            assert get_config_dir().exists()
            cfg = load_config()
            cfg.setdefault("profiles", {})["a@example.com"] = {"verified_email": "a@example.com"}
            save_config(cfg)
            assert load_config()["profiles"]["a@example.com"]["verified_email"] == "a@example.com"
        finally:
            if old_config_dir is None:
                os.environ.pop("HTMLEMAIL_CONFIG_DIR", None)
            else:
                os.environ["HTMLEMAIL_CONFIG_DIR"] = old_config_dir

    validate_sender_identity("a@example.com", {"email": "A@Example.com"})
    try:
        validate_sender_identity("a@example.com", {"email": "b@example.com"})
    except HtmlemailError as exc:
        assert "Authenticated Google account" in str(exc)
    else:
        raise AssertionError("sender mismatch should fail")

    typer.echo("✓ Tests passed")


def main(
    markdown_file: Path | None = typer.Argument(None, help="Markdown file path to convert"),
    email: list[str] = typer.Option(None, "--email", help="Send email via Gmail API; repeat for multiple recipients"),
    cc: list[str] = typer.Option(None, "--cc", help="CC email address; repeat for multiple recipients"),
    from_email: str | None = typer.Option(None, "--from", help="Gmail account to authenticate and send from"),
    base_url: str | None = typer.Option(None, "--base-url", help="Base URL used to resolve relative href/src links"),
    init: bool = typer.Option(False, "--init", help="Copy OAuth client secrets into the app config directory"),
    client_secrets: Path | None = typer.Option(None, "--client-secrets", help="Path to Google OAuth desktop client secrets JSON"),
    show_config_flag: bool = typer.Option(False, "--show-config", help="Show config, credentials, token paths, and known profiles"),
    logout_from_email: str | None = typer.Option(None, "--logout-from", help="Delete the saved token/profile for this sender"),
    reauth: bool = typer.Option(False, "--reauth", help="Force a new OAuth login for --from"),
    token: Path | None = typer.Option(None, "--token", help="Deprecated: explicit token path override for migration/debugging"),
    test: bool = typer.Option(False, "--test", help="Run inline tests and exit"),
) -> None:
    """Convert markdown to email-friendly HTML, or send it through Gmail.

    Examples:

        uv run htmlemail.py --init --client-secrets ~/Downloads/credentials.json
        uv run htmlemail.py post.md --base-url https://example.com/blog/post/
        uv run htmlemail.py post.md --from you@gmail.com --email friend@example.com
    """
    try:
        if test:
            run_tests()
            raise typer.Exit(0)

        if init:
            if not client_secrets:
                raise HtmlemailError("--init requires --client-secrets PATH")
            target = init_config(client_secrets)
            eprint(f"✓ Saved OAuth client secrets to {target}")
            if not markdown_file and not show_config_flag:
                raise typer.Exit(0)

        if logout_from_email:
            logout_from(logout_from_email)
            if not markdown_file and not show_config_flag:
                raise typer.Exit(0)

        if show_config_flag:
            show_config()
            if not markdown_file:
                raise typer.Exit(0)

        if not markdown_file:
            raise HtmlemailError("markdown_file is required unless --test, --init, --show-config, or --logout-from is used")

        if not markdown_file.exists():
            raise HtmlemailError(f"File not found: {markdown_file}")

        rendered = render_email(markdown_file, base_url)
        for warning in rendered.warnings:
            eprint(f"Warning: {warning}")

        if email:
            if not from_email:
                raise HtmlemailError("--from EMAIL is required when sending mail")
            if token:
                eprint("Warning: --token is deprecated; use --from EMAIL sender profiles for normal operation.")
            eprint(f"Sending email from {normalized_email(from_email)} to {', '.join(email)}...")
            creds, sender = get_credentials_for_sender(from_email, token, reauth)
            gmail_service = build("gmail", "v1", credentials=creds)
            send_email(gmail_service, sender, email, rendered.subject, rendered.html, cc or [])
            eprint(f"✓ Email sent to {', '.join(email)} with subject: {rendered.subject}")
        else:
            typer.echo(rendered.html)
    except HtmlemailError as exc:
        eprint(f"Error: {exc}")
        raise typer.Exit(1) from exc


if __name__ == "__main__":
    typer.run(main)
