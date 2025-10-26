#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "typer>=0.12",
#   "httpx>=0.27",
#   "google-auth>=2.27",
#   "google-auth-oauthlib>=1.2",
#   "rich>=13.7",
#   "python-dotenv",
# ]
# ///

"""Minimal, elegant Gmail search CLI."""

import asyncio
import json
import typer
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence
from rich.console import Console
from pathlib import Path
from httpx import AsyncClient
from google_oauth import ensure_token, api
from email.utils import parseaddr, parsedate_to_datetime
from dotenv import load_dotenv
from datetime import timezone


Message = Dict[str, Any]
MessageRow = Dict[str, Any]
Messages = AsyncIterator[Message]


load_dotenv()
HEADERS = ("Date", "From", "To", "Subject")
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
GMAIL_TOKEN_FILE = Path("~/.config/sanand-scripts/token.gmail.json").expanduser()


async def iter_message_refs(client: AsyncClient, q: str, page_size: int, limit: int) -> Messages:
    """Yield message refs up to the requested limit."""
    remaining = limit
    token: Optional[str] = None
    while remaining > 0:
        params = {"q": q, "maxResults": min(page_size, remaining)}
        if token:
            params["pageToken"] = token
        data = await api(client, "GET", "/messages", params=params)
        msgs = data.get("messages", [])
        if not msgs:
            return
        for msg in msgs:
            yield msg
            remaining -= 1
            if remaining == 0:
                return
        token = data.get("nextPageToken")
        if not token:
            return


async def get_metadata(client: AsyncClient, msg_id: str) -> Message:
    """Fetch per-message metadata only with selected headers."""
    params = {"format": "metadata"}
    for h in HEADERS:
        params.setdefault("metadataHeaders", []).append(h)
    return await api(client, "GET", f"/messages/{msg_id}", params=params)


async def iter_details(client: AsyncClient, refs: Messages, concurrency: int = 16) -> Messages:
    """Yield details with bounded concurrency by processing refs in chunks."""
    chunk: List[Message] = []
    async for ref in refs:
        chunk.append(ref)
        if len(chunk) == concurrency:
            for item in await asyncio.gather(*[get_metadata(client, r["id"]) for r in chunk]):
                yield item
            chunk.clear()
    if chunk:
        for item in await asyncio.gather(*[get_metadata(client, r["id"]) for r in chunk]):
            yield item


def fmt_date(s: str) -> str:
    """Format RFC2822 date to yyyy-mm-dd hh:mm (local)."""
    if not s:
        return ""
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        # Gmail occasionally omits timezone metadata; returning the raw header keeps output usable.
        return s


FIELDS = {
    "id": lambda m, hm: m.get("id", ""),
    "date": lambda m, hm: fmt_date(hm.get("date", "")),
    "from": lambda m, hm: hm.get("from", ""),
    "email": lambda m, hm: parseaddr(hm.get("from", ""))[1],
    "to": lambda m, hm: hm.get("to", ""),
    "subject": lambda m, hm: hm.get("subject", ""),
    "snippet": lambda m, hm: m.get("snippet", ""),
    "labels": lambda m, hm: ",".join(m.get("labelIds", [])),
    "size": lambda m, hm: m.get("sizeEstimate", ""),
}


def to_row(m: Message, fields: Sequence[str]) -> MessageRow:
    """Convert Gmail message to selected fields."""
    headers = {
        h.get("name", "").lower(): h.get("value", "")
        for h in m.get("payload", {}).get("headers", [])
    }
    return {field: FIELDS[field](m, headers) for field in fields if field in FIELDS}


def print_tsv(con: Console, row: Dict[str, Any], fields: Sequence[str]) -> None:
    """Render a TSV row with colorized columns."""
    c = ["cyan", "magenta", "green", "white", "blue", "yellow"]
    v = [str(row.get(f, "")) for f in fields]
    con.print("\t".join(f"[{c[i % len(c)]}]{x}[/{c[i % len(c)]}]" for i, x in enumerate(v)))


app = typer.Typer(add_completion=False, no_args_is_help=True, help="Search Gmail.")


@app.command(context_settings={"allow_extra_args": False, "ignore_unknown_options": False})
async def main(
    q: str = typer.Argument("in:inbox", help="Gmail search query (Gmail search syntax)."),
    user_id: str = typer.Option("me", "--user", help="Gmail user: 'me' or email."),
    limit: int = typer.Option(20, "-n", "--limit", min=1, help="Total results to print."),
    fields: List[str] = typer.Option(
        ["date", "from", "subject", "snippet"],
        "--fields",
        help=(
            "Fields to print; repeat or separate with commas/spaces. "
            f"Valid: {', '.join(FIELDS.keys())}"
        ),
    ),
    jsonl: bool = typer.Option(False, "--jsonl", help="Emit JSONL (one object per line)."),
    reauth: bool = typer.Option(False, "--reauth", help="Force login"),
):
    """Search Gmail and print messages in a clean table or JSONL.

    Examples:\n
    - gmail --limit 50 "from:example.com"  # list 50 recent inbox emails\n
    - gmail --fields date,email "subject:invoice"  # show date and only sender email\n
    - gmail --fields "date, from, subject" in:archive  # comma/space separated fields\n
    - gmail --jsonl --fields "email subject" "has:attachment newer_than:1y"  # JSONL output\n
    """
    tok = ensure_token(scopes=GMAIL_SCOPES, token_file=GMAIL_TOKEN_FILE, force_auth=reauth)
    if not tok:
        return
    base = f"https://gmail.googleapis.com/gmail/v1/users/{user_id}"
    headers_http = {"Authorization": f"Bearer {tok}", "Accept": "application/json"}

    async with AsyncClient(base_url=base, headers=headers_http, timeout=30) as client:
        sel_fields = [part.strip() for value in fields for part in value.replace(",", " ").split()]
        if not sel_fields:
            return

        if not jsonl:
            con = Console(highlight=False)
            con.print("\t".join(sel_fields))

        page_size = limit if limit <= 500 else 500
        refs = iter_message_refs(client=client, q=q, page_size=page_size, limit=limit)
        async for detail in iter_details(client, refs):
            row = to_row(detail, sel_fields)
            if jsonl:
                print(json.dumps(row, ensure_ascii=False))
                continue
            print_tsv(con, row, sel_fields)


if __name__ == "__main__":
    app()
