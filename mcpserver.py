#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.14"
# dependencies = ["fastmcp>=3.4,<4"]
# ///

# Usage: uv run mcpserver.py
#   Exposes an MCP server on localhost:2428 that lets LLMs run bash commands.
#   curl localhost:2428/mcp to test
# Test with
#   just test-mcpserver

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict
from urllib import parse, request

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_context, get_http_request
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    TextContent,
    TextResourceContents,
)

# Initialize the server
mcp = FastMCP("Remote shell commands")
LOG_DIR = Path.home() / ".local/share/sanand-scripts/mcpserver"
MAX_LINE_BYTES = 50 * 1024
TRIM_PREFIX_BYTES = 49 * 1024
TRIM_MARKER = "... [trimmed to 50KB/line] ..."
MAX_TOTAL_OUTPUT_BYTES = 512 * 1024
TOTAL_OUTPUT_HEAD_BYTES = 384 * 1024
TOTAL_TRIM_MARKER = "\n... [omitted {bytes} bytes to keep total output under 512 KiB] ...\n"
MAX_UPLOAD_BYTES = int(os.environ.get("MCPSERVER_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
BASH_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcpserver-bash")


def output_schema(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


DOWNLOAD_FILE_OUTPUT_SCHEMA = output_schema(
    {
        "path": {"type": "string"},
        "mime_type": {"type": "string"},
        "encoding": {"type": "string", "enum": ["utf-8", "base64"]},
        "size": {"type": "integer", "minimum": 0},
        "bytes_read": {"type": "integer", "minimum": 0},
    }
)
BASH_OUTPUT_SCHEMA = output_schema(
    {
        "server_start_id": {"type": "string"},
        "request_id": {"type": ["string", "null"]},
        "started_at": {"type": "string"},
        "finished_at": {"type": "string"},
        "duration_ms": {"type": "number", "minimum": 0},
        "exit_code": {"type": ["integer", "null"]},
        "status": {"type": "string", "enum": ["success", "failed", "timeout", "error"]},
        "ok": {"type": "boolean"},
        "timed_out": {"type": "boolean"},
        "error": {"type": ["string", "null"]},
        "cwd": {"type": "string"},
        "output": {"type": "string"},
        "output_path": {"type": ["string", "null"]},
        "stdout_bytes": {"type": "integer", "minimum": 0},
        "stderr_bytes": {"type": "integer", "minimum": 0},
        "output_bytes_before_limits": {"type": "integer", "minimum": 0},
        "output_bytes_after_limits": {"type": "integer", "minimum": 0},
        "line_trim_count": {"type": "integer", "minimum": 0},
        "line_trim_omitted_bytes": {"type": "integer", "minimum": 0},
        "total_limit_omitted_bytes": {"type": "integer", "minimum": 0},
        "total_truncation_omitted_bytes": {"type": "integer", "minimum": 0},
    }
)
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
MOUNTED_PATHS = [
    ("~/code/scripts/agents/*/SKILL.md", "coding + thinking skills"),
    ("~/code/blog/pages/skills/*/SKILL.md", "thinking skills"),
    (
        "~/Dropbox/notes/transcripts/YYYY-MM-DD*.md",
        "date-window by filename, then read narrow ranges",
    ),
    ("~/Dropbox/notes/about/*.md", "people or company specific notes"),
    ("~/Dropbox/notes/", "notes archive; recently edited files are useful"),
    (
        "~/Documents/data/s.anand@gramener.com/",
        "work email, chat, calendar exports. Use `gws` for latest",
    ),
    (
        "~/Documents/data/root.node@gmail.com/",
        "personal email, calendar exports. Use `gws` for latest",
    ),
    (
        "~/Documents/data/whatsapp/",
        "WhatsApp exports. Use `jaq` fields `.time`, `.author`, `.text`",
    ),
    (
        "~/Documents/data/browsing-history.db",
        "SELECT url, timestamp, visit_count, ... FROM activity",
    ),
    (
        "~/Documents/Mail/{*.mbox,mail-index.sqlite}",
        "2005-2025 email archives (use ?immutable=1)",
    ),
    ("~/Documents/data/linkedin-invites.json", "LinkedIn invites"),
    ("~/Documents/chatgpt/", "ChatGPT chat dumps"),
    ("~/Documents/claude/", "Claude chat dumps"),
    ("~/code/talks/README.md", "talk transcripts, slides"),
    ("~/code/datastories/config.json", "data stories"),
    ("~/code/llmdemos/config.json", "innovation team demos"),
    ("~/code/llmevals/README.md", "LLM evals"),
    (
        "~/code/blog/description.md",
        '20K files, 5K posts. Search for "- llm" for AI-related posts',
    ),
    ("~/code/til/README.md", "things I learnt"),
    ("~/code/README.md", "code repos"),
    ("~/r2/files/podcast", "podcasts written for myself"),
    ("~/Documents/activities/", "daily activity logs"),
]


class ChatGPTUpload(TypedDict):
    """File reference injected by ChatGPT for an openai/fileParams parameter."""

    download_url: str
    file_id: str
    file_name: str
    mime_type: str


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


def markdown_code_block(text: str) -> str:
    fence = "```"
    while fence in text:
        fence += "`"
    return f"{fence}\n{text}\n{fence}"


def markdown_json(data: Any) -> str:
    return markdown_code_block(json.dumps(data, indent=2, default=str, ensure_ascii=False))


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
            "session_id": headers.get("mcp-session-id"),
            "protocol_version": headers.get("mcp-protocol-version"),
        }
        return info
    return None


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), default=str, ensure_ascii=False) + "\n")


def write_markdown_log(event: dict[str, Any]) -> None:
    operation = event["operation"]
    if operation not in {"bash", "download_file", "save_file"}:
        return
    now = datetime.now(UTC)
    timestamp = now.strftime("%Y-%m-%dT%H-%M-%S.%f")
    sections = [f"# mcpserver {operation} log {timestamp}"]
    if operation == "bash":
        sections += [
            "## Command",
            markdown_code_block(event["commands"]),
            "## Request",
            markdown_json(event["request"]),
            "## Output",
            markdown_code_block(event["output"]),
        ]
    sections += ["## Result", markdown_json(event["result"])]
    path = LOG_DIR / now.strftime("%Y-%m") / f"{timestamp}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def write_request_log(event: dict[str, Any]) -> None:
    http = event.get("http") or {}
    record = {
        "server_start_id": event["server_start_id"],
        "timestamp": event["timestamp"],
        "session_id": http.get("session_id"),
        "mcp_method": event.get("method"),
        "http_path": http.get("path"),
        "user_agent": http.get("user_agent"),
        "protocol_version": http.get("protocol_version") or event.get("protocol_version"),
        "client_name": event.get("client_name"),
        "client_version": event.get("client_version"),
        "client_capabilities": event.get("client_capabilities"),
        "duration_ms": event.get("duration_ms"),
        "result": event.get("result"),
        "error": event.get("error"),
    }
    append_jsonl(
        LOG_DIR / f"requests-{datetime.now():%Y-%m-%d}.jsonl",
        {key: value for key, value in record.items() if value is not None},
    )


def log_event(operation: str, **data: Any) -> dict[str, Any]:
    """Append one compact, machine-readable tool event."""
    http = http_request_info()
    event = {
        "timestamp": iso_timestamp(),
        "server_start_id": SERVER_START_ID,
        "operation": operation,
        **({"http": http} if http else {}),
        **data,
    }
    append_jsonl(LOG_DIR / "events.jsonl", event)
    if operation == "request":
        write_request_log(event)
    else:
        write_markdown_log(event)
    if http and http.get("session_id"):
        (LOG_DIR / "latest-session").write_text(str(http["session_id"]), encoding="utf-8")
    return event


def client_metadata(context: MiddlewareContext[Any]) -> dict[str, Any]:
    message = context.message.model_dump()
    params = message.get("params") or {}
    client = params.get("clientInfo") or {}
    return {
        key: value
        for key, value in {
            "protocol_version": params.get("protocolVersion"),
            "client_name": client.get("name"),
            "client_version": client.get("version"),
            "client_capabilities": params.get("capabilities"),
        }.items()
        if value is not None
    }


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
            log_event(
                "request",
                method=context.method,
                **client_metadata(context),
                duration_ms=round((time.monotonic() - start) * 1000, 3),
                error=repr(e),
            )
            raise
        log_event(
            "request",
            method=context.method,
            **client_metadata(context),
            duration_ms=round((time.monotonic() - start) * 1000, 3),
            result=type(result).__name__,
        )
        return result


class IgnoreUnknownParametersMiddleware(Middleware):
    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, ToolResult],
    ) -> ToolResult:
        tool = await mcp.get_tool(context.message.name)
        if tool is None:
            return await call_next(context)
        arguments = context.message.arguments or {}
        unknown = arguments.keys() - tool.parameters.get("properties", {})
        if unknown:
            await context.fastmcp_context.warning(
                f"Unknown parameters will be ignored: {', '.join(sorted(unknown))}"
            )
            for name in unknown:
                arguments.pop(name)
        return await call_next(context)


mcp.add_middleware(RequestLogMiddleware())
mcp.add_middleware(IgnoreUnknownParametersMiddleware())


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


def log_startup_record() -> dict[str, Any]:
    record = {
        "server_start_id": SERVER_START_ID,
        "timestamp": iso_timestamp(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
    }
    append_jsonl(LOG_DIR / "startup.jsonl", record)
    print(mounted_paths_text(), flush=True)
    return record


def finalize_output(
    output: str,
    result: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    before_limits = len(output.encode())
    line_limited, line_trim_count, line_omitted = trim_long_lines_with_stats(output)
    total_limited, total_omitted = limit_total_output(line_limited)
    output_path = None
    if line_omitted or total_omitted:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix="mcpserver-output-", suffix=".txt", delete=False
        ) as handle:
            handle.write(output)
            output_path = handle.name
    result.update(
        {
            "output_path": output_path,
            "output_bytes_before_limits": before_limits,
            "output_bytes_after_limits": len(total_limited.encode()),
            "line_trim_count": line_trim_count,
            "line_trim_omitted_bytes": line_omitted,
            "total_limit_omitted_bytes": total_omitted,
            "total_truncation_omitted_bytes": line_omitted + total_omitted,
        }
    )
    return total_limited, result


def run_bash_command(commands: str, timeout_ms: int, cwd: str | None = None) -> tuple[str, dict[str, Any]]:
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
        "cwd": str(Path(cwd).expanduser().resolve() if cwd else Path.cwd().resolve()),
        "stdout_bytes": 0,
        "stderr_bytes": 0,
    }
    try:
        if not commands.strip():
            raise ValueError("commands must not be empty")
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be greater than zero")
        completed = subprocess.run(
            commands,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            cwd=Path(cwd).expanduser() if cwd else None,
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
    if result["timed_out"]:
        result["status"] = "timeout"
    elif result["error"] is not None:
        result["status"] = "error"
    elif result["exit_code"] == 0:
        result["status"] = "success"
    else:
        result["status"] = "failed"
    result["ok"] = result["status"] == "success"
    result["finished_at"] = iso_timestamp()
    result["duration_ms"] = round((time.monotonic() - start) * 1000, 3)
    return finalize_output(output, result)


def display_path(path: Path) -> str:
    path = path.absolute()
    home = Path.home().absolute()
    try:
        relative = path.relative_to(home)
    except ValueError:
        return str(path)
    return "~" if relative == Path(".") else f"~/{relative}"


def path_access_mode(path: Path) -> str:
    writable = os.access(path, os.W_OK, effective_ids=True)
    with suppress(OSError):
        writable = writable and not os.statvfs(path).f_flag & os.ST_RDONLY
    return "rw" if writable else "ro"


def mount_probe_path(display: str) -> Path:
    parts = []
    for part in Path(display).expanduser().parts:
        if any(marker in part for marker in "*?[{"):
            break
        parts.append(part)
    return Path(*parts)


def mounted_paths_text(mounted_paths: list[tuple[str, str]] | None = None) -> str:
    entries = []
    for display, description in MOUNTED_PATHS if mounted_paths is None else mounted_paths:
        path = mount_probe_path(display)
        if path.exists():
            entries.append(f"  {path_access_mode(path)}: {display} - {description}")
    return "mounted paths (rw = read-write, ro = read-only):\n" + ("\n".join(entries) if entries else "(none detected)")


def build_bash_description(
    cwd: Path | None = None,
    mounted_paths: list[tuple[str, str]] | None = None,
) -> str:
    cwd = cwd or Path.cwd()
    return f"""Runs multiline bash script. Prints output.

cwd: {display_path(cwd)} ({path_access_mode(cwd)})

{mounted_paths_text(mounted_paths)}

Avoid broad scans over large file lists - `$HOME`, `~/.*`, `~/code`, `~/Documents`, or archives - unless necessary.
  Scope to known subdirs. Prefer `fd`/`rg` to respect `.gitignore` and shrink long listings.
  Check shape (dir count, file size, match count, ...) first.
Avoid wasting tool calls on wrong files by
  Verifying paths with `pwd`, `ls`, or `test -e`.
  Locating best candidates with `fd`, `rg -l`, `rga -l`, READMEs/configs/indexes.
  Searching best matches with `path:line` evidence.
Paths contain spaces. Prefer null-delimited loops (`fd -0`, `xargs -0`).

This is not Code Interpreter. There's no `/mnt/data`. Use /tmp or user/repo paths.

CLI tools: fd --max-depth 3 --type f, rg, rga for binary docs, jaq (faster jq), duckdb/sqlite3, sg (at search), git/gh, agent-browser, ...
Before using an unfamiliar/version-sensitive CLI, inspect `--help` / `--version`; do not infer flags.
Before querying structured data, inspect its type/schema/sample first (JSON vs JSONL, keys, columns).
Before lint/test/build, inspect project-native verification (`just --list`, package scripts, pyproject, Makefile, AGENTS.md); run focused checks before full suites.
For ad-hoc Python, prefer `uv run --no-project --with pkg1 --with pkg2 -- python - <<'PY'`.
Avoid running AI agents (codex, claude, gemini, ...) unless the user explicitly requests it.
Commands run transactionally; do not start persistent background servers.

gws can access work email, calendar, chat, drive:
  gws gmail users messages list --params '{{"userId":"me", "q": "from:..."}}'
  gws calendar events list --params '{{"calendarId":"s.anand@straive.com","timeMin":"...","timeMax":"...","singleEvents":true,"orderBy":"startTime"}}'
For personal email (root.node@gmail.com) use:
  GOOGLE_WORKSPACE_CLI_CONFIG_DIR="$HOME/.config/gws-root.node@gmail.com" gws gmail users messages list --params '{{"userId":"me", "q": "from:..."}}'

Prefer `set -euo pipefail` for deterministic scripts. If so, then:
  Handle expected misses (`rg ... || true`, `test -e`, optional files) printing concise diagnostics.
  Capped pipelines like `rg ... | head` can exit 141 from SIGPIPE.
  Wrap expected capped/no-match pipelines in `( ... | head -N || true )`.
Batch related probes into one script with section headers.
  Avoid re-running identical discovery commands unless new evidence changed the scope.
Batch multiple commands into fewer tool calls to avoid call overhead.

stdout longer than {MAX_LINE_BYTES} bytes / line and over {MAX_TOTAL_OUTPUT_BYTES} bytes is trimmed.
When output is trimmed, the complete output is saved to `output_path`; use `download_file` if needed.
Save larger text or binaries to /tmp and use `download_file` tool to transfer.

Do not print secrets, tokens, or credentials, unless explicitly requested.
Summarize and cite paths/lines instead.
"""


async def bash(commands: str, timeout_ms: int = 30_000, cwd: str | None = None) -> ToolResult:
    ctx: Context = get_context()
    await ctx.info(f"bash: {commands} (cwd={cwd or os.getcwd()})")
    output, result = await asyncio.get_running_loop().run_in_executor(
        BASH_EXECUTOR, run_bash_command, commands, timeout_ms, cwd
    )
    request_id = getattr(ctx, "request_id", None)
    result["request_id"] = str(request_id) if request_id is not None else None
    if result["stderr_bytes"]:
        await ctx.warning(f"ERROR: {result['stderr_bytes']} stderr bytes")
    await ctx.info(f"DONE: {len(output.encode())} bytes, return code {result['exit_code']}")
    request = {"server_start_id": SERVER_START_ID, "timeout_ms": timeout_ms, "cwd": cwd}
    log_event("bash", commands=commands, request=request, output=output, result=result)
    result["output"] = output
    return ToolResult(
        content=[TextContent(type="text", text=output)],
        structured_content=result,
        is_error=not result["ok"],
    )


bash.__doc__ = build_bash_description()
mcp.tool(description=bash.__doc__, output_schema=BASH_OUTPUT_SCHEMA)(bash)


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


def read_error(action: str, path: Path, error: OSError) -> ToolError:
    return ToolError(f"{action}: {path}: {error.strerror or error}")


def _download_file(path: str) -> ToolResult:
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

    try:
        with file_path.open("rb") as handle:
            data = handle.read()
    except PermissionError as error:
        raise read_error("Permission denied", file_path, error) from error
    except OSError as error:
        raise read_error("Cannot read file", file_path, error) from error

    mime_type = file_mime_type(file_path, data[:8192])
    text = None
    if is_text_mime_type(mime_type):
        with suppress(UnicodeDecodeError):
            text = data.decode()
    uri = file_path.as_uri()
    if text is not None:
        resource = TextResourceContents(uri=uri, mimeType=mime_type, text=text)
        encoding = "utf-8"
    else:
        resource = BlobResourceContents(
            uri=uri,
            mimeType=mime_type,
            blob=base64.b64encode(data).decode("ascii"),
        )
        encoding = "base64"

    metadata = {
        "path": str(file_path),
        "mime_type": mime_type,
        "encoding": encoding,
        "size": file_stat.st_size,
        "bytes_read": len(data),
    }
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(metadata, separators=(",", ":"))),
            EmbeddedResource(type="resource", resource=resource),
        ],
        structured_content=metadata,
    )


@mcp.tool(
    annotations={"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    output_schema=DOWNLOAD_FILE_OUTPUT_SCHEMA,
)
async def download_file(path: str) -> ToolResult:
    """Download large/binary files as an MCP embedded resource. Use bash tool for small text."""
    result = _download_file(path)
    metadata = result.structured_content
    await get_context().info(f"download_file: {metadata['path']} ({metadata['size']} bytes)")
    log_event("download_file", result=metadata)
    return result


def writable_roots() -> list[Path]:
    """Return detected writable working and mounted directories."""
    candidates = [Path.cwd(), *(mount_probe_path(display) for display, _ in MOUNTED_PATHS)]
    roots = []
    for candidate in candidates:
        if candidate.is_file():
            candidate = candidate.parent
        if candidate.is_dir() and path_access_mode(candidate) == "rw":
            resolved = candidate.resolve()
            if resolved not in roots:
                roots.append(resolved)
    return roots


def _save_file(file: ChatGPTUpload, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Stream a ChatGPT-uploaded file to an allowed writable local path."""
    required = {"download_url", "file_id", "file_name", "mime_type"}
    missing = required - file.keys()
    if missing or any(not isinstance(file.get(name), str) or not file[name] for name in required):
        raise ToolError(f"Invalid file object; required string fields: {', '.join(sorted(required))}")
    url = file["download_url"]
    if parse.urlsplit(url).scheme.lower() != "https":
        raise ToolError("download_url must use HTTPS")

    path = Path(destination).expanduser().resolve()
    if not any(path.is_relative_to(root) for root in writable_roots()):
        raise ToolError(f"Destination is not under a detected writable root: {path}")
    if path.exists() and not overwrite:
        raise ToolError(f"Destination already exists (set overwrite=true to replace it): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    size = 0
    temp_path: Path | None = None
    try:
        with request.urlopen(request.Request(url, headers={"User-Agent": "mcpserver/1"}), timeout=30) as response:
            if parse.urlsplit(response.geturl()).scheme.lower() != "https":
                raise ToolError("download_url redirected to a non-HTTPS URL")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > MAX_UPLOAD_BYTES:
                raise ToolError(f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte size limit")
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
                temp_path = Path(handle.name)
                while chunk := response.read(64 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ToolError(f"Upload exceeds the {MAX_UPLOAD_BYTES}-byte size limit")
                    handle.write(chunk)
                    digest.update(chunk)
        if overwrite:
            os.replace(temp_path, path)
        else:
            try:
                os.link(temp_path, path)
            except FileExistsError as error:
                raise ToolError(
                    f"Destination already exists (set overwrite=true to replace it): {path}"
                ) from error
            temp_path.unlink()
        temp_path = None
    except ToolError:
        raise
    except Exception as error:
        raise ToolError(f"Could not save upload: {error}") from error
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    result = {
        "path": str(path),
        "size": size,
        "mime_type": file["mime_type"],
        "sha256": digest.hexdigest(),
        "file_id": file["file_id"],
    }
    return result


@mcp.tool(
    meta={"openai/fileParams": ["file"]},
    annotations={
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def save_file(file: ChatGPTUpload, destination: str, overwrite: bool = False) -> dict[str, Any]:
    """Stream a ChatGPT-uploaded file to an allowed writable local path."""
    result = _save_file(file, destination, overwrite)
    await get_context().info(f"save_file: {result['path']} ({result['size']} bytes)")
    log_event("save_file", result=result)
    return result


def latest_session_id() -> str:
    with suppress(OSError):
        return (LOG_DIR / "latest-session").read_text(encoding="utf-8").strip()
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
