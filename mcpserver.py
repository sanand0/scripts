#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.14"
# dependencies = ["fastmcp"]
# ///

# Usage: uv run mcpserver.py
#   Exposes an MCP server on localhost:2428 that lets LLMs run bash commands.
#   curl localhost:2428/mcp to test
# npx -y ngrok@latest http --host-header=rewrite 2428
#   Exposes the server to the internet via ngrok. (Use with caution!)

import subprocess
import json
import os
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_context, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

# Initialize the server
mcp = FastMCP("Remote shell commands")
LOG_DIR = Path.home() / ".local/share/sanand-scripts/mcpserver"
MAX_LINE_BYTES = 50 * 1024
TRIM_PREFIX_BYTES = 49 * 1024
TRIM_MARKER = "... [trimmed to 50KB/line] ..."


def markdown_code_block(text: str) -> str:
    """Return text in a fence that cannot be closed by the content."""
    ticks = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            ticks = max(ticks, current)
        else:
            current = 0
    fence = "`" * max(3, ticks + 1)
    return f"{fence}\n{text}\n{fence}"


def fit_utf8_prefix(text: str, byte_count: int) -> str:
    return text.encode()[:byte_count].decode(errors="ignore")


def fit_utf8_suffix(text: str, byte_count: int) -> str:
    return text.encode()[-byte_count:].decode(errors="ignore")


def trim_long_line(line: str) -> str:
    if len(line.encode()) <= MAX_LINE_BYTES:
        return line
    suffix_bytes = MAX_LINE_BYTES - TRIM_PREFIX_BYTES - len(TRIM_MARKER.encode())
    return fit_utf8_prefix(line, TRIM_PREFIX_BYTES) + TRIM_MARKER + fit_utf8_suffix(line, suffix_bytes)


def trim_long_lines(text: str) -> str:
    return "".join(
        trim_long_line(line.removesuffix("\n")) + ("\n" if line.endswith("\n") else "")
        for line in text.splitlines(keepends=True)
    )


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S.%f")


def markdown_json(data: Any) -> str:
    return markdown_code_block(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def serialize_message(message: Any) -> Any:
    for method in ("model_dump", "dict"):
        if hasattr(message, method):
            return getattr(message, method)()
    return repr(message)


def http_request_info(body: str | None = None) -> dict[str, Any] | None:
    with suppress(RuntimeError):
        request = get_http_request()
        scope = request.scope
        info: dict[str, Any] = {
            "method": request.method,
            "url": str(request.url),
            "path": scope.get("path"),
            "query_string": scope.get("query_string", b"").decode(errors="replace"),
            "client": scope.get("client"),
            "server": scope.get("server"),
            "headers": [
                {
                    "name": name.decode("latin-1", errors="replace"),
                    "value": value.decode("latin-1", errors="replace"),
                }
                for name, value in scope.get("headers", [])
            ],
        }
        if body is not None:
            info["body"] = body
        return info
    return None


def request_metadata(
    *,
    ctx: Context | None = None,
    middleware_context: MiddlewareContext[Any] | None = None,
    extra: dict[str, Any] | None = None,
    http_body: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "http": http_request_info(body=http_body),
        "mcp": {},
    }
    if ctx is not None:
        for name in ("request_id", "client_id", "session_id"):
            with suppress(Exception):
                data["mcp"][name] = getattr(ctx, name)
    if middleware_context is not None:
        data["mcp"].update(
            {
                "source": middleware_context.source,
                "type": middleware_context.type,
                "method": middleware_context.method,
                "timestamp": middleware_context.timestamp.isoformat(),
                "message": serialize_message(middleware_context.message),
            }
        )
    if extra:
        data["metadata"] = extra
    return data


def write_markdown_log(title: str, body: str) -> None:
    logged_at = timestamp()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"{logged_at}.md").write_text(f"# {title} {logged_at}\n\n{body}")


def log_request_event(event: str, metadata: dict[str, Any]) -> None:
    write_markdown_log(
        f"mcpserver request {event}",
        f"## Event\n\n{event}\n\n## Request\n\n{markdown_json(metadata)}\n",
    )


async def current_http_body() -> str | None:
    with suppress(RuntimeError):
        return trim_long_lines((await get_http_request().body()).decode(errors="replace"))
    return None


def log_bash_command(commands: str, output: str, request: dict[str, Any]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S.%f")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"{timestamp}.md").write_text(
        f"# mcpserver bash log {timestamp}\n\n"
        f"## Command\n\n{markdown_code_block(commands)}\n\n"
        f"## Request\n\n{markdown_json(request)}\n\n"
        f"## Output\n\n{markdown_code_block(output)}\n",
    )


class RequestLogMiddleware(Middleware):
    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        body = await current_http_body()
        opened = request_metadata(middleware_context=context, http_body=body)
        log_request_event("opened", opened)
        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as e:
            closed = request_metadata(middleware_context=context, http_body=body)
            closed["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
            closed["error"] = repr(e)
            log_request_event("closed", closed)
            raise
        closed = request_metadata(middleware_context=context, http_body=body)
        closed["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
        closed["result_type"] = type(result).__name__
        log_request_event("closed", closed)
        return result


mcp.add_middleware(RequestLogMiddleware())


def load_env_token(name: str) -> str:
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("'\"")
    return os.environ.get(name, "")


def matching_cloudflared_running(token: str) -> bool:
    for cmdline_path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            parts = cmdline_path.read_bytes().split(b"\0")
        except OSError:
            continue
        if not parts or Path(parts[0].decode(errors="ignore")).name != "cloudflared":
            continue
        if token in " ".join(part.decode(errors="ignore") for part in parts):
            return True
    return False


def start_cloudflare_tunnel() -> subprocess.Popen[str] | None:
    token = load_env_token("CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN")
    if not token:
        raise RuntimeError("CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN not found in .env")
    if matching_cloudflared_running(token):
        return None
    log_dir = Path.home() / ".local/share/sanand-scripts/mcpserver-cloudflared"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now():%Y-%m-%d-%H-%M-%S}.jsonl"
    return subprocess.Popen(
        ["cloudflared", "tunnel", "--logfile", str(log_path), "run", "--token", token],
        text=True,
    )


def stop_cloudflare_tunnel(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@mcp.tool()
async def bash(commands: str, timeout_ms: int = 30_000) -> str:
    """Runs multiline bash script.
Under `~` = `/home/vscode/` (`/home/sanand` also works) you have:

- ~/Dropbox/notes/transcripts/YYYY-MM-DD*.md - date-window by filename, then read narrow ranges
- ~/Dropbox/notes/about/*.md - people or company specific notes
- ~/Documents/data/
  - s.anand@gramener.com/ and root.node@gmail.com/ - email, chat, calendar exports. Use `gws` for latest
  - whatsapp/ - whatsapp exports. Use `jaq` fields `.time`, `.author`, `.text`.
  - browsing-history.db (SELECT url, timestamp, visit_count, ... FROM activity)
  - linkedin-invites.json
- ~/code/talks/README.md - talk transcripts, slides
- ~/code/datastories/config.json - data stories
- ~/code/llmdemos/config.json - innovation team demos
- ~/code/llmevals/README.md - LLM evals
- ~/code/blog/description.md - 20K files, 5K posts. Search for "- llm" for AI-related posts.
- ~/code/til/README.md - things I learnt
- ~/code/scripts/agents/*/SKILL.md - agent skills
- ~/code/README.md - code repos
- ~/r2/files/podcast - podcasts written for myself
- ~/Documents/activities/ - daily activity logs

Avoid broad scans over `$HOME`, `~/.*`, `~/code`, `~/Documents`, or archives unless necessary.
  Scope to known subdirs. Prefer `fd`/`rg` because they respect `.gitignore` by default.
  Check shape (dir count, file size, match count, ...) first.
First locate candidate files with `fd`, `rg -l`, `rga -l`, READMEs/configs/indexes.
  THEN inspect the best files with `path:line` evidence.
  Paths contain spaces. Prefer null-delimited loops (`fd -0`, `xargs -0`).

This is not Code Interpreter. There's no `/mnt/data`. Use /tmp or user/repo paths.

CLI tools: fd --max-depth 3 --type f, rg, rga for binary docs, jaq (faster jq), duckdb/sqlite3, sg (at search), git/gh, agent-browser, ...
Prefer `uv run --with pkg1 --with pkg2 -- python - <<'PY'` over `python`.

gws can access email, calendar, chat:
  gws gmail users messages list --params '{"userId":"me", "q": "from:..."}'
  gws calendar events list --params '{"calendarId":"s.anand@straive.com","timeMin":"...","timeMax":"...","singleEvents":true,"orderBy":"startTime"}'

Verify paths with `pwd`, `ls`, or `test -e` before deep scans.
Use `set -euo pipefail` for deterministic scripts.
  Handle expected misses (`rg ... || true`, `test -e`, optional files) printing concise diagnostics.
  Capped pipelines like `rg ... | head` can exit 141 from SIGPIPE.
  Wrap expected capped/no-match pipelines in `( ... | head -N || true )`.
Batch related probes into one script with section headers.
  Avoid re-running identical discovery commands unless new evidence changed the scope.

Keep stdout bounded to ~200 lines/ ~20KB.
  Save large intermediate output to /tmp; print only summaries and paths.

Do not print secrets, tokens, or credentials, unless explicitly requested.
Summarize and cite paths/lines instead.
"""
    ctx: Context = get_context()
    await ctx.info(f"bash: {commands}")
    request = request_metadata(ctx=ctx, extra={"timeout_ms": timeout_ms})
    try:
        result = subprocess.run(
            commands,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except Exception as e:
        output = trim_long_lines(str(e))
        log_bash_command(commands, output, request)
        return output
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
        await ctx.warning(f"ERROR: {result.stderr}")
    if result.returncode != 0:
        output += f"\nReturn code: {result.returncode}"
    output = trim_long_lines(output)
    await ctx.info(f"DONE: {len(output)} chars, return code {result.returncode}")
    log_bash_command(commands, output, request)
    return output


if __name__ == "__main__":
    tunnel = start_cloudflare_tunnel()
    try:
        mcp.run(transport="http", port=2428)
    finally:
        stop_cloudflare_tunnel(tunnel)
