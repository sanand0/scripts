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

import base64
import hashlib
import json
import mimetypes
import os
import stat
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import AudioContent, BlobResourceContents, EmbeddedResource, ImageContent, TextContent

# Initialize the server
mcp = FastMCP("Remote shell commands")
LOG_DIR = Path.home() / ".local/share/sanand-scripts/mcpserver"
MAX_LINE_BYTES = 50 * 1024
TRIM_PREFIX_BYTES = 49 * 1024
TRIM_MARKER = "... [trimmed to 50KB/line] ..."
MAX_TOTAL_OUTPUT_BYTES = 512 * 1024
TOTAL_OUTPUT_HEAD_BYTES = 384 * 1024
TOTAL_TRIM_MARKER = "\n... [omitted {bytes} bytes to keep total output under 512 KiB] ...\n"
DEFAULT_READ_BYTES = 8 * 1024 * 1024
MAX_READ_BYTES = 16 * 1024 * 1024
SERVER_START_ID = uuid.uuid4().hex
RATE_TAGS = {
    "intent_miss",
    "source_miss",
    "version_miss",
    "too_much_evidence",
    "too_little_evidence",
    "tool_failure",
    "unsupported_conclusion",
}


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


def trim_long_line(line: str) -> tuple[str, int]:
    original_bytes = len(line.encode())
    if original_bytes <= MAX_LINE_BYTES:
        return line, 0
    suffix_bytes = MAX_LINE_BYTES - TRIM_PREFIX_BYTES - len(TRIM_MARKER.encode())
    trimmed = fit_utf8_prefix(line, TRIM_PREFIX_BYTES) + TRIM_MARKER + fit_utf8_suffix(line, suffix_bytes)
    return trimmed, original_bytes - len(trimmed.encode())


def trim_long_lines_with_stats(text: str) -> tuple[str, int, int]:
    chunks = []
    trim_count = 0
    omitted_bytes = 0
    for line in text.splitlines(keepends=True):
        trimmed, omitted = trim_long_line(line.removesuffix("\n"))
        chunks.append(trimmed + ("\n" if line.endswith("\n") else ""))
        if omitted:
            trim_count += 1
            omitted_bytes += omitted
    return "".join(chunks), trim_count, omitted_bytes


def trim_long_lines(text: str) -> str:
    return trim_long_lines_with_stats(text)[0]


def limit_total_output(text: str) -> tuple[str, int]:
    data = text.encode()
    if len(data) <= MAX_TOTAL_OUTPUT_BYTES:
        return text, 0
    omitted = len(data) - MAX_TOTAL_OUTPUT_BYTES
    while True:
        marker = TOTAL_TRIM_MARKER.format(bytes=omitted)
        tail_bytes = MAX_TOTAL_OUTPUT_BYTES - TOTAL_OUTPUT_HEAD_BYTES - len(marker.encode())
        limited = fit_utf8_prefix(text, TOTAL_OUTPUT_HEAD_BYTES) + marker + fit_utf8_suffix(text, tail_bytes)
        new_omitted = len(data) - len(limited.encode())
        if new_omitted == omitted:
            return limited, omitted
        omitted = new_omitted


def iso_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def markdown_json(data: Any) -> str:
    return markdown_code_block(json.dumps(data, indent=2, default=str, ensure_ascii=False))


def serialize_message(message: Any) -> Any:
    for method in ("model_dump", "dict"):
        if hasattr(message, method):
            return getattr(message, method)()
    return repr(message)


def http_request_info() -> dict[str, Any] | None:
    with suppress(RuntimeError):
        request = get_http_request()
        scope = request.scope
        headers = {
            name.decode("latin-1", errors="replace").lower(): value.decode("latin-1", errors="replace")
            for name, value in scope.get("headers", [])
        }
        info: dict[str, Any] = {
            "path": scope.get("path"),
            "user_agent": headers.get("user-agent"),
        }
        return info
    return None


def request_metadata(
    *,
    ctx: Context | None = None,
    middleware_context: MiddlewareContext[Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "server_start_id": SERVER_START_ID,
        "http": http_request_info(),
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


def request_log_record(metadata: dict[str, Any]) -> dict[str, Any]:
    http = metadata.get("http") or {}
    mcp_data = metadata.get("mcp") or metadata
    message = mcp_data.get("message") or {}
    params = message.get("params") if isinstance(message, dict) else {}
    result = {
        "server_start_id": SERVER_START_ID,
        "timestamp": iso_timestamp(),
        "request_id": metadata.get("request_id") or mcp_data.get("request_id"),
        "session_id": metadata.get("session_id") or mcp_data.get("session_id"),
        "mcp_method": metadata.get("method") or mcp_data.get("method"),
        "http_path": http.get("path") or metadata.get("http_path"),
        "user_agent": http.get("user_agent") or metadata.get("user_agent"),
        "protocol_version": metadata.get("protocol_version") or mcp_data.get("protocol_version"),
        "duration_ms": metadata.get("duration_ms"),
    }
    if isinstance(params, dict):
        result["protocol_version"] = result["protocol_version"] or params.get("protocolVersion")
    if "result" in metadata:
        result["result"] = metadata["result"]
    if "error" in metadata:
        result["error"] = metadata["error"]
    return {key: value for key, value in result.items() if value is not None}


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), default=str, ensure_ascii=False) + "\n")


def log_request_close(metadata: dict[str, Any]) -> dict[str, Any]:
    record = request_log_record(metadata)
    append_jsonl(LOG_DIR / f"requests-{datetime.now():%Y-%m-%d}.jsonl", record)
    return record


def log_bash_command(commands: str, output: str, request: dict[str, Any], result: dict[str, Any]) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S.%f")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    (LOG_DIR / f"{timestamp}.md").write_text(
        f"# mcpserver bash log {timestamp}\n\n"
        f"## Command\n\n{markdown_code_block(commands)}\n\n"
        f"## Request\n\n{markdown_json(request)}\n\n"
        f"## Output\n\n{markdown_code_block(output)}\n\n"
        f"## Result\n\n{markdown_json(result)}\n",
    )


class RequestLogMiddleware(Middleware):
    async def on_request(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        start = time.monotonic()
        try:
            result = await call_next(context)
        except Exception as e:
            closed = request_metadata(middleware_context=context)
            closed["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
            closed["error"] = repr(e)
            log_request_close(closed)
            raise
        closed = request_metadata(middleware_context=context)
        closed["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
        closed["result"] = type(result).__name__
        log_request_close(closed)
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


def git_state() -> dict[str, Any]:
    repo = Path(__file__).resolve().parent
    commit = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--short=12", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    )
    return {"commit": commit or None, "dirty": dirty}


def tool_description_hash() -> str:
    return hashlib.sha256((bash.__doc__ or "").encode()).hexdigest()


def log_startup_record() -> dict[str, Any]:
    record = {
        "server_start_id": SERVER_START_ID,
        "timestamp": iso_timestamp(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "git": git_state(),
        "tool_description_hash": tool_description_hash(),
    }
    append_jsonl(LOG_DIR / "startup.jsonl", record)
    return record


def finalize_output(
    output: str,
    result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    before_limits = len(output.encode())
    line_limited, line_trim_count, line_omitted = trim_long_lines_with_stats(output)
    total_limited, total_omitted = limit_total_output(line_limited)
    result.update(
        {
            "output_bytes_before_limits": before_limits,
            "output_bytes_after_limits": len(total_limited.encode()),
            "line_trim_count": line_trim_count,
            "line_trim_omitted_bytes": line_omitted,
            "total_limit_omitted_bytes": total_omitted,
            "total_truncation_omitted_bytes": line_omitted + total_omitted,
        }
    )
    return total_limited, result


def run_bash_command(commands: str, timeout_ms: int) -> tuple[str, dict[str, Any]]:
    started_at = iso_timestamp()
    start = time.monotonic()
    result: dict[str, Any] = {
        "server_start_id": SERVER_START_ID,
        "started_at": started_at,
        "finished_at": None,
        "duration_ms": None,
        "exit_code": None,
        "timed_out": False,
        "error": None,
        "stdout_bytes": 0,
        "stderr_bytes": 0,
    }
    try:
        completed = subprocess.run(
            commands,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
        result["exit_code"] = completed.returncode
        result["stdout_bytes"] = len(completed.stdout.encode())
        result["stderr_bytes"] = len(completed.stderr.encode())
        output = completed.stdout
        if completed.stderr:
            output += f"\nSTDERR:\n{completed.stderr}"
        if completed.returncode != 0:
            output += f"\nReturn code: {completed.returncode}"
    except subprocess.TimeoutExpired as e:
        result["timed_out"] = True
        result["error"] = str(e)
        stdout = e.stdout or ""
        stderr = e.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        result["stdout_bytes"] = len(stdout.encode())
        result["stderr_bytes"] = len(stderr.encode())
        output = stdout
        if stderr:
            output += f"\nSTDERR:\n{stderr}"
        output += f"\nCommand timed out after {timeout_ms} ms: {e}"
    except Exception as e:
        result["error"] = repr(e)
        output = str(e)
    result["finished_at"] = iso_timestamp()
    result["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
    return finalize_output(output, result)


@mcp.tool()
async def bash(commands: str, timeout_ms: int = 30_000) -> str:
    """Runs multiline bash script.
Under `~` = `/home/vscode/` (`/home/sanand` also works) you have:

Skills already on Claude, not yet on ChatGPT:
~/code/scripts/agents/*/SKILL.md - coding + thinking skills
~/code/blog/pages/skills/*/SKILL.md - thinking skills

Content:
~/Dropbox/notes/transcripts/YYYY-MM-DD*.md - date-window by filename, then read narrow ranges
~/Dropbox/notes/about/*.md - people or company specific notes
~/Documents/data/
  s.anand@gramener.com/ and root.node@gmail.com/ - email, chat, calendar exports. Use `gws` for latest
  whatsapp/ - whatsapp exports. Use `jaq` fields `.time`, `.author`, `.text`.
  browsing-history.db (SELECT url, timestamp, visit_count, ... FROM activity)
  linkedin-invites.json
~/code/talks/README.md - talk transcripts, slides
~/code/datastories/config.json - data stories
~/code/llmdemos/config.json - innovation team demos
~/code/llmevals/README.md - LLM evals
~/code/blog/description.md - 20K files, 5K posts. Search for "- llm" for AI-related posts.
~/code/til/README.md - things I learnt
~/code/README.md - code repos
~/r2/files/podcast - podcasts written for myself
~/Documents/activities/ - daily activity logs

Avoid broad scans over `$HOME`, `~/.*`, `~/code`, `~/Documents`, or archives unless necessary.
  Scope to known subdirs. Prefer `fd`/`rg` because they respect `.gitignore` by default.
  Check shape (dir count, file size, match count, ...) first.
First locate candidate files with `fd`, `rg -l`, `rga -l`, READMEs/configs/indexes.
  THEN inspect the best files with `path:line` evidence.
  Paths contain spaces. Prefer null-delimited loops (`fd -0`, `xargs -0`).
Avoid running AI agents (codex, claude, gemini, ...) unless the user explicitly requests it.

This is not Code Interpreter. There's no `/mnt/data`. Use /tmp or user/repo paths.

CLI tools: fd --max-depth 3 --type f, rg, rga for binary docs, jaq (faster jq), duckdb/sqlite3, sg (at search), git/gh, agent-browser, ...
For ad-hoc Python outside a project, prefer `uv run --no-project --with pkg1 --with pkg2 -- python - <<'PY'`.
For project commands, `cd` into the project and use its environment normally.

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
    request = {"server_start_id": SERVER_START_ID, "timeout_ms": timeout_ms}
    output, result = run_bash_command(commands, timeout_ms)
    if result["stderr_bytes"]:
        await ctx.warning(f"ERROR: {result['stderr_bytes']} stderr bytes")
    await ctx.info(f"DONE: {len(output.encode())} bytes, return code {result['exit_code']}")
    log_bash_command(commands, output, request, result)
    return output


def is_text_mime_type(mime_type: str) -> bool:
    return (
        mime_type.startswith("text/")
        or mime_type in {"application/json", "application/javascript", "application/xml"}
        or mime_type.endswith(("+json", "+xml"))
    )


def looks_like_utf8_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return all(char.isprintable() or char in "\t\n\r" for char in text)


def file_mime_type(path: Path, sample: bytes) -> str:
    mime_type = mimetypes.guess_type(path.name, strict=False)[0]
    if mime_type is None and looks_like_utf8_text(sample):
        return "text/plain"
    return mime_type or "application/octet-stream"


def decode_utf8_chunk(data: bytes, *, offset: int, eof: bool) -> tuple[str, int] | None:
    if offset and data and data[0] & 0b1100_0000 == 0b1000_0000:
        raise ToolError(f"offset {offset} is not on a UTF-8 character boundary")
    trims = range(1) if eof else range(min(3, len(data)) + 1)
    for trim in trims:
        candidate = data if trim == 0 else data[:-trim]
        try:
            return candidate.decode("utf-8"), len(candidate)
        except UnicodeDecodeError:
            continue
    return None


def read_error(action: str, path: Path, error: OSError) -> ToolError:
    return ToolError(f"{action}: {path}: {error.strerror or error}")


@mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": False}, output_schema=None)
def read(path: str, offset: int = 0, limit: int = DEFAULT_READ_BYTES) -> ToolResult:
    """Read a local text or binary file using MCP-native content blocks.

    Text is returned as UTF-8. Images and audio use native MCP media blocks;
    other binary files use base64 embedded resources. Reads are capped at 16
    MiB per call. If `eof` is false, call again with the returned `next_offset`.
    Byte offsets must fall on a UTF-8 character boundary for text files.
    """
    if offset < 0:
        raise ToolError("offset must be non-negative")
    if not 1 <= limit <= MAX_READ_BYTES:
        raise ToolError(f"limit must be between 1 and {MAX_READ_BYTES} bytes")

    file_path = Path(path).expanduser().resolve()
    try:
        file_stat = file_path.stat()
    except FileNotFoundError as error:
        raise read_error("File not found", file_path, error) from error
    except PermissionError as error:
        raise read_error("Permission denied", file_path, error) from error
    except OSError as error:
        raise read_error("Cannot inspect file", file_path, error) from error
    if not stat.S_ISREG(file_stat.st_mode):
        raise ToolError(f"Not a regular file: {file_path}")
    if offset > file_stat.st_size:
        raise ToolError(f"offset {offset} exceeds file size {file_stat.st_size}")

    try:
        with file_path.open("rb") as handle:
            sample = handle.read(8192)
            handle.seek(offset)
            data = handle.read(limit)
    except PermissionError as error:
        raise read_error("Permission denied", file_path, error) from error
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error

    mime_type = file_mime_type(file_path, sample)
    text_chunk = None
    if is_text_mime_type(mime_type):
        text_chunk = decode_utf8_chunk(data, offset=offset, eof=offset + len(data) == file_stat.st_size)
    if text_chunk is not None:
        text, bytes_read = text_chunk
        if data and bytes_read == 0:
            raise ToolError("limit is too small for the next UTF-8 character")
        payload = TextContent(type="text", text=text)
        encoding = "utf-8"
    else:
        bytes_read = len(data)
        encoded = base64.b64encode(data).decode("ascii")
        complete = offset == 0 and bytes_read == file_stat.st_size
        if complete and mime_type.startswith("image/"):
            payload = ImageContent(type="image", data=encoded, mimeType=mime_type)
        elif complete and mime_type.startswith("audio/"):
            payload = AudioContent(type="audio", data=encoded, mimeType=mime_type)
        else:
            end = offset + bytes_read
            uri = file_path.as_uri() if complete else f"{file_path.as_uri()}#bytes={offset}-{end}"
            payload = EmbeddedResource(
                type="resource",
                resource=BlobResourceContents(
                    uri=uri,
                    mimeType=mime_type if complete else "application/octet-stream",
                    blob=encoded,
                ),
            )
        encoding = "base64"

    next_offset = offset + bytes_read
    eof = next_offset == file_stat.st_size
    metadata = {
        "path": str(file_path),
        "mime_type": mime_type,
        "encoding": encoding,
        "size": file_stat.st_size,
        "offset": offset,
        "bytes_read": bytes_read,
        "next_offset": None if eof else next_offset,
        "eof": eof,
    }
    return ToolResult(
        content=[TextContent(type="text", text=json.dumps(metadata, separators=(",", ":"))), payload],
        structured_content=metadata,
    )


def latest_session_id() -> str:
    for path in sorted(LOG_DIR.glob("requests-*.jsonl"), reverse=True):
        with suppress(OSError, json.JSONDecodeError):
            for line in reversed(path.read_text().splitlines()):
                session_id = json.loads(line).get("session_id")
                if session_id:
                    return session_id
    return ""


def mcp_rate(args: list[str]) -> int:
    if not args or args[0] not in {"0", "1", "2"}:
        raise SystemExit("Usage: mcp-rate SCORE [TAG] [NOTE...] where SCORE is 0|1|2")
    score = args[0]
    tag = args[1] if len(args) > 1 else ""
    if tag and tag not in RATE_TAGS:
        raise SystemExit(f"Tag must be one of: {', '.join(sorted(RATE_TAGS))}")
    note = " ".join(args[2:]) if len(args) > 2 else ""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "ratings.tsv").open("a", encoding="utf-8") as handle:
        handle.write(f"{iso_timestamp()}\t{latest_session_id()}\t{score}\t{tag}\t{note}\n")
    return 0


if __name__ == "__main__":
    if Path(sys.argv[0]).name == "mcp-rate" or (len(sys.argv) > 1 and sys.argv[1] == "mcp-rate"):
        offset = 1 if Path(sys.argv[0]).name == "mcp-rate" else 2
        raise SystemExit(mcp_rate(sys.argv[offset:]))
    log_startup_record()
    tunnel = start_cloudflare_tunnel()
    try:
        mcp.run(transport="http", port=2428)
    finally:
        stop_cloudflare_tunnel(tunnel)
