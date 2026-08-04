from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import (
    BlobResourceContents,
    EmbeddedResource,
    TextContent,
    TextResourceContents,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcpserver


@pytest.fixture(autouse=True)
def isolate_log_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")


def test_trim_long_lines_keeps_each_line_under_50kb() -> None:
    line = "a" * (60 * 1024)

    trimmed = mcpserver.trim_long_lines(f"small\n{line}\nend")
    long_line = trimmed.splitlines()[1]

    assert len(long_line.encode()) == mcpserver.MAX_LINE_BYTES
    assert long_line.startswith("a" * mcpserver.TRIM_PREFIX_BYTES)
    assert mcpserver.TRIM_MARKER in long_line
    assert trimmed.splitlines() == ["small", long_line, "end"]


def test_limit_total_output_preserves_utf8_head_and_tail() -> None:
    text = ("α" * (390 * 1024)) + "MIDDLE" + ("Ω" * (140 * 1024))

    limited, omitted = mcpserver.limit_total_output(text)

    encoded = limited.encode()
    assert len(encoded) <= mcpserver.MAX_TOTAL_OUTPUT_BYTES
    assert limited.startswith("α" * 1000)
    assert limited.endswith("Ω" * 1000)
    assert "MIDDLE" not in limited
    assert f"omitted {omitted} bytes" in limited
    assert omitted == len(text.encode()) - len(encoded)


def test_log_event_writes_compact_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")

    output, result = mcpserver.run_bash_command("printf ok", timeout_ms=1000)
    mcpserver.log_event(
        "bash",
        commands="printf ok",
        request={"server_start_id": "start-test", "timeout_ms": 1000, "cwd": None},
        output=output,
        result=result,
    )

    [line] = (tmp_path / "events.jsonl").read_text().splitlines()
    event = json.loads(line)
    assert event["operation"] == "bash"
    assert event["server_start_id"] == "start-test"
    assert event["commands"] == "printf ok"
    assert event["output"] == "ok"
    assert event["result"]["exit_code"] == 0
    assert event["result"]["output_bytes_after_limits"] == 2
    [log_path] = tmp_path.glob("????-??/*.md")
    markdown = log_path.read_text()
    assert markdown.index("## Command") < markdown.index("## Request") < markdown.index("## Output")
    assert markdown.index("## Output") < markdown.index("## Result")
    assert "printf ok" in markdown


def test_run_bash_command_records_nonzero_timeout_and_cwd(tmp_path) -> None:
    cwd_output, _ = mcpserver.run_bash_command("pwd", timeout_ms=1000, cwd=str(tmp_path))
    output, result = mcpserver.run_bash_command("printf err >&2; exit 7", timeout_ms=1000)

    assert cwd_output.strip() == str(tmp_path)
    assert "STDERR:\nerr" in output
    assert "Return code: 7" in output
    assert result["exit_code"] == 7
    assert result["timed_out"] is False
    assert result["stderr_bytes"] == 3

    timeout_output, timeout_result = mcpserver.run_bash_command("sleep 1", timeout_ms=1)

    assert "timed out" in timeout_output
    assert timeout_result["exit_code"] is None
    assert timeout_result["timed_out"] is True
    assert timeout_result["error"]


def test_bash_returns_structured_nonzero_result_without_tool_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("bash", {"commands": "printf no >&2; exit 7", "cwd": str(tmp_path)})

    result = asyncio.run(exercise_tool())

    assert result.is_error is False
    assert "Return code: 7" in result.content[0].text
    assert result.structured_content["exit_code"] == 7
    assert result.structured_content["timed_out"] is False
    assert result.structured_content["cwd"] == str(tmp_path.resolve())
    assert result.structured_content["stderr_bytes"] == 2
    assert result.structured_content["request_id"]
    assert result.structured_content["server_start_id"] == mcpserver.SERVER_START_ID


def test_bash_timeout_is_tool_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool(
                "bash", {"commands": "sleep 1", "timeout_ms": 1}, raise_on_error=False
            )

    result = asyncio.run(exercise_tool())

    assert result.is_error is True
    assert result.structured_content["timed_out"] is True


def test_bash_invalid_input_is_structured_tool_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("bash", {"commands": " "}, raise_on_error=False)

    result = asyncio.run(exercise_tool())

    assert result.is_error is True
    assert result.structured_content["exit_code"] is None
    assert "commands must not be empty" in result.structured_content["error"]


def test_startup_record_is_compact_jsonl_and_prints_mounts(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")

    record = mcpserver.log_startup_record()

    [line] = (tmp_path / "startup.jsonl").read_text().splitlines()
    logged = json.loads(line)
    assert logged == record
    assert logged["server_start_id"] == "start-test"
    assert logged["pid"] > 0
    assert logged["cwd"]
    assert capsys.readouterr().out.startswith("mounted paths (rw = read-write, ro = read-only):\n")


def test_cloudflare_tunnel_reuses_matching_process_or_starts_owned_one(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "load_env_token", lambda name: "secret-token")
    monkeypatch.setattr(mcpserver.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(mcpserver, "matching_cloudflared_running", lambda token: True)

    assert mcpserver.start_cloudflare_tunnel() is None

    started = object()
    calls = []
    monkeypatch.setattr(mcpserver, "matching_cloudflared_running", lambda token: False)
    monkeypatch.setattr(
        mcpserver.subprocess,
        "Popen",
        lambda command, text: calls.append((command, text)) or started,
    )

    assert mcpserver.start_cloudflare_tunnel() is started
    command, text = calls[0]
    assert command[:3] == ["cloudflared", "tunnel", "--logfile"]
    assert command[-3:] == ["run", "--token", "secret-token"]
    assert text is True


def test_cloudflare_tunnel_cleanup_kills_after_timeout() -> None:
    class Process:
        killed = False
        terminated = False

        def poll(self):
            return None

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            if not self.killed:
                raise mcpserver.subprocess.TimeoutExpired("cloudflared", timeout)

        def kill(self):
            self.killed = True

    process = Process()
    mcpserver.stop_cloudflare_tunnel(process)

    assert process.terminated is True
    assert process.killed is True


def test_log_event_records_safe_http_context_and_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")
    monkeypatch.setattr(
        mcpserver,
        "http_request_info",
        lambda: {
            "path": "/mcp",
            "user_agent": "agent/1",
            "session_id": "sess-1",
            "protocol_version": "2025-06-18",
        },
    )

    record = mcpserver.log_event(
        "request",
        method="initialize",
        protocol_version="2025-03-26",
        client_name="ChatGPT",
        client_version="1.2.3",
        client_capabilities={"sampling": {}},
        duration_ms=12.3,
        result="ok",
    )

    assert json.loads((tmp_path / "events.jsonl").read_text()) == record
    assert record == {
        "server_start_id": "start-test",
        "timestamp": record["timestamp"],
        "operation": "request",
        "http": {
            "path": "/mcp",
            "user_agent": "agent/1",
            "session_id": "sess-1",
            "protocol_version": "2025-06-18",
        },
        "method": "initialize",
        "protocol_version": "2025-03-26",
        "client_name": "ChatGPT",
        "client_version": "1.2.3",
        "client_capabilities": {"sampling": {}},
        "duration_ms": 12.3,
        "result": "ok",
    }
    assert (tmp_path / "latest-session").read_text() == "sess-1"
    [request_path] = tmp_path.glob("requests-*.jsonl")
    request_record = json.loads(request_path.read_text())
    assert request_record == {
        "server_start_id": "start-test",
        "timestamp": record["timestamp"],
        "session_id": "sess-1",
        "mcp_method": "initialize",
        "http_path": "/mcp",
        "user_agent": "agent/1",
        "protocol_version": "2025-06-18",
        "client_name": "ChatGPT",
        "client_version": "1.2.3",
        "client_capabilities": {"sampling": {}},
        "duration_ms": 12.3,
        "result": "ok",
    }


def test_client_metadata_extracts_initialize_fields_without_request_arguments() -> None:
    class Message:
        def model_dump(self):
            return {
                "params": {
                    "protocolVersion": "2025-03-26",
                    "clientInfo": {"name": "ChatGPT", "version": "1.2.3"},
                    "capabilities": {"sampling": {}},
                    "arguments": {"token": "secret"},
                }
            }

    class Context:
        message = Message()

    metadata = mcpserver.client_metadata(Context())

    assert metadata == {
        "protocol_version": "2025-03-26",
        "client_name": "ChatGPT",
        "client_version": "1.2.3",
        "client_capabilities": {"sampling": {}},
    }
    assert "secret" not in json.dumps(metadata)


def test_mcp_rate_appends_latest_session_score(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "latest_session_id", lambda: "sess-latest")

    mcpserver.mcp_rate(["2", "tool_failure", "command timed out"])

    [line] = (tmp_path / "ratings.tsv").read_text().splitlines()
    timestamp, session_id, score, tag, note = line.split("\t")
    assert timestamp
    assert session_id == "sess-latest"
    assert score == "2"
    assert tag == "tool_failure"
    assert note == "command timed out"


def test_latest_session_id_reads_correlation_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    assert mcpserver.latest_session_id() == ""

    (tmp_path / "latest-session").write_text("current-session\n")
    assert mcpserver.latest_session_id() == "current-session"


def test_download_file_returns_complete_utf8_embedded_resource(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("Hello, αβ!", encoding="utf-8")

    result = mcpserver._download_file(str(path))

    assert result.structured_content == {
        "path": str(path.resolve()),
        "mime_type": "text/plain",
        "encoding": "utf-8",
        "size": path.stat().st_size,
        "bytes_read": path.stat().st_size,
    }
    assert isinstance(result.content[0], TextContent)
    assert json.loads(result.content[0].text) == result.structured_content
    assert isinstance(result.content[1], EmbeddedResource)
    assert isinstance(result.content[1].resource, TextResourceContents)
    assert result.content[1].resource.text == "Hello, αβ!"


@pytest.mark.parametrize(
    ("name", "data", "mime_type"),
    [
        ("pixel.png", b"\x89PNG\r\n\x1a\ncontent", "image/png"),
        ("sound.mp3", b"ID3content", "audio/mpeg"),
        ("document.pdf", b"%PDF-1.7\ncontent", "application/pdf"),
    ],
)
def test_download_file_returns_complete_binary_embedded_resource(tmp_path, name, data, mime_type) -> None:
    path = tmp_path / name
    path.write_bytes(data)

    result = mcpserver._download_file(str(path))

    payload = result.content[1]
    assert isinstance(payload, EmbeddedResource)
    assert isinstance(payload.resource, BlobResourceContents)
    assert result.structured_content["mime_type"] == mime_type
    assert result.structured_content["encoding"] == "base64"
    assert payload.resource.mimeType == mime_type
    assert base64.b64decode(payload.resource.blob) == data


def test_download_file_transfers_binary_larger_than_bash_output_cap(tmp_path) -> None:
    data = b"\0\1" * (8 * 1024 * 1024 + 1)
    path = tmp_path / "large.bin"
    path.write_bytes(data)

    result = mcpserver._download_file(str(path))

    assert result.structured_content["bytes_read"] > mcpserver.MAX_TOTAL_OUTPUT_BYTES
    assert base64.b64decode(result.content[1].resource.blob) == data


def test_download_file_treats_invalid_utf8_text_as_blob(tmp_path) -> None:
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"\xff")

    result = mcpserver._download_file(str(path))

    assert isinstance(result.content[1].resource, BlobResourceContents)
    assert result.content[1].resource.mimeType == "text/plain"
    assert base64.b64decode(result.content[1].resource.blob) == b"\xff"


def test_download_file_empty_and_unknown_utf8_files(tmp_path) -> None:
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    extensionless = tmp_path / "README"
    extensionless.write_text("plain text", encoding="utf-8")

    empty_result = mcpserver._download_file(str(empty))
    text_result = mcpserver._download_file(str(extensionless))

    assert empty_result.structured_content["bytes_read"] == 0
    assert base64.b64decode(empty_result.content[1].resource.blob) == b""
    assert text_result.structured_content["mime_type"] == "text/plain"
    assert text_result.content[1].resource.text == "plain text"


def test_download_file_reports_filesystem_errors(tmp_path, monkeypatch) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content")

    with pytest.raises(ToolError, match="File not found"):
        mcpserver._download_file(str(tmp_path / "missing.txt"))
    with pytest.raises(ToolError, match="Not a regular file"):
        mcpserver._download_file(str(tmp_path))

    original_open = Path.open

    def deny_open(self, *args, **kwargs):
        if self == path:
            raise PermissionError(13, "Permission denied", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(ToolError, match="Permission denied"):
        mcpserver._download_file(str(path))


def test_download_file_tool_is_registered_read_only_and_callable(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello")
    logs = []

    async def handle_log(log):
        logs.append(log)

    async def exercise_tool():
        async with Client(mcpserver.mcp, log_handler=handle_log) as client:
            tools = await client.list_tools()
            result = await client.call_tool("download_file", {"path": str(path)})
            return tools, result

    tools, result = asyncio.run(exercise_tool())
    download_tool = next(tool for tool in tools if tool.name == "download_file")
    assert all(tool.name != "read" for tool in tools)
    assert download_tool.annotations.readOnlyHint is True
    assert download_tool.annotations.openWorldHint is False
    assert download_tool.outputSchema == mcpserver.DOWNLOAD_FILE_OUTPUT_SCHEMA
    assert result.is_error is False
    assert result.structured_content["path"] == str(path.resolve())
    assert result.content[1].resource.text == "hello"
    assert [log.data["msg"] for log in logs if log.level == "info"] == [
        f"download_file: {path.resolve()} (5 bytes)"
    ]
    [event] = [
        event
        for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()
        if (event := json.loads(line))["operation"] == "download_file"
    ]
    assert event["operation"] == "download_file"
    assert event["result"]["size"] == 5
    [log_path] = (tmp_path / "logs").glob("????-??/*.md")
    assert "# mcpserver download_file log " in log_path.read_text()


def test_save_file_streams_chatgpt_upload_under_writable_root(tmp_path, monkeypatch) -> None:
    data = b"hello upload"

    class Response:
        def __init__(self):
            self.headers = {"Content-Length": str(len(data))}

        def __enter__(self):
            self.remaining = data
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            chunk, self.remaining = self.remaining[:size], self.remaining[size:]
            return chunk

        def geturl(self):
            return "https://files.openai.com/upload"

    monkeypatch.setattr(mcpserver, "writable_roots", lambda: [tmp_path.resolve()])
    monkeypatch.setattr(mcpserver.request, "urlopen", lambda *args, **kwargs: Response())
    destination = tmp_path / "uploads" / "hello.txt"
    logs = []

    async def handle_log(log):
        logs.append(log)

    async def exercise_tool():
        async with Client(mcpserver.mcp, log_handler=handle_log) as client:
            return await client.call_tool(
                "save_file",
                {
                    "file": {
                        "download_url": "https://files.openai.com/upload",
                        "file_id": "file-123",
                        "file_name": "hello.txt",
                        "mime_type": "text/plain",
                    },
                    "destination": str(destination),
                },
            )

    result = asyncio.run(exercise_tool())

    assert destination.read_bytes() == data
    assert result.structured_content == {
        "path": str(destination.resolve()),
        "size": len(data),
        "mime_type": "text/plain",
        "sha256": hashlib.sha256(data).hexdigest(),
        "file_id": "file-123",
    }
    assert [log.data["msg"] for log in logs if log.level == "info"] == [
        f"save_file: {destination.resolve()} ({len(data)} bytes)"
    ]
    [event] = [
        event
        for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()
        if (event := json.loads(line))["operation"] == "save_file"
    ]
    assert event["operation"] == "save_file"
    assert event["result"]["size"] == len(data)
    [log_path] = (tmp_path / "logs").glob("????-??/*.md")
    assert "# mcpserver save_file log " in log_path.read_text()


def test_save_file_rejects_traversal_overwrite_http_and_oversize(tmp_path, monkeypatch) -> None:
    root = tmp_path / "root"
    root.mkdir()
    existing = root / "existing.txt"
    existing.write_text("keep")
    monkeypatch.setattr(mcpserver, "writable_roots", lambda: [root.resolve()])
    upload = {
        "download_url": "https://files.openai.com/upload",
        "file_id": "file-123",
        "file_name": "hello.txt",
        "mime_type": "text/plain",
    }

    with pytest.raises(ToolError, match="writable root"):
        mcpserver._save_file(upload, str(root / ".." / "escape.txt"))
    with pytest.raises(ToolError, match="already exists"):
        mcpserver._save_file(upload, str(existing))
    with pytest.raises(ToolError, match="HTTPS"):
        mcpserver._save_file({**upload, "download_url": "http://example.com/file"}, str(root / "new.txt"))

    class TooLargeResponse:
        def __init__(self):
            self.headers = {"Content-Length": str(mcpserver.MAX_UPLOAD_BYTES + 1)}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def geturl(self):
            return "https://files.openai.com/upload"

    monkeypatch.setattr(mcpserver.request, "urlopen", lambda *args, **kwargs: TooLargeResponse())
    with pytest.raises(ToolError, match="size limit"):
        mcpserver._save_file(upload, str(root / "large.txt"))


def test_save_file_tool_has_chatgpt_meta_and_write_annotations() -> None:
    async def list_tools():
        async with Client(mcpserver.mcp) as client:
            return await client.list_tools()

    tools = asyncio.run(list_tools())
    save_tool = next(tool for tool in tools if tool.name == "save_file")
    bash_tool = next(tool for tool in tools if tool.name == "bash")

    assert save_tool.inputSchema["properties"]["file"]["type"] == "object"
    assert save_tool.inputSchema["properties"]["file"]["properties"] == {
            "download_url": {"type": "string"},
            "file_id": {"type": "string"},
            "file_name": {"type": "string"},
            "mime_type": {"type": "string"},
        }
    assert save_tool.inputSchema["properties"]["file"]["required"] == [
            "download_url",
            "file_id",
            "file_name",
            "mime_type",
        ]

    assert save_tool.meta["openai/fileParams"] == ["file"]
    assert save_tool.annotations.readOnlyHint is False
    assert save_tool.annotations.destructiveHint is True
    assert save_tool.annotations.openWorldHint is True
    assert bash_tool.outputSchema == mcpserver.BASH_OUTPUT_SCHEMA


def test_bash_tool_exposes_and_uses_cwd_and_dynamic_mount_description(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def list_tools():
        async with Client(mcpserver.mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool("bash", {"commands": "pwd", "cwd": str(tmp_path)})
            return tools, result

    tools, result = asyncio.run(list_tools())
    bash_tool = next(tool for tool in tools if tool.name == "bash")
    assert "cwd" in bash_tool.inputSchema["properties"]
    assert f"cwd: {mcpserver.display_path(Path.cwd())} (" in bash_tool.description
    assert "mounted paths (rw = read-write, ro = read-only):" in bash_tool.description
    assert "download_file" in bash_tool.description
    assert result.content[0].text.strip() == str(tmp_path)


def test_tools_warn_and_ignore_unknown_parameters(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")
    path = tmp_path / "hello.txt"
    path.write_text("hello")
    logs = []

    async def handle_log(log):
        logs.append(log)

    async def exercise_tool():
        async with Client(mcpserver.mcp, log_handler=handle_log) as client:
            bash_result = await client.call_tool(
                "bash",
                {"commands": "printf ok", "description": "Print a test value"},
            )
            download_result = await client.call_tool(
                "download_file",
                {"path": str(path), "description": "Download a test file"},
            )
            return bash_result, download_result

    bash_result, download_result = asyncio.run(exercise_tool())

    assert bash_result.content[0].text == "ok"
    assert download_result.content[1].resource.text == "hello"
    assert sum(
        log.level == "warning"
        and log.data["msg"] == "Unknown parameters will be ignored: description"
        for log in logs
    ) == 2


def test_build_bash_description_omits_unmounted_paths(tmp_path, monkeypatch) -> None:
    mounted = tmp_path / "mounted path"
    mounted.mkdir()
    missing = tmp_path / "missing"
    monkeypatch.setattr(mcpserver, "path_access_mode", lambda path: "ro")

    description = mcpserver.build_bash_description(
        cwd=tmp_path,
        mounted_paths=[
            (f"{mounted}/*.md", "available"),
            (f"{missing}/*.md", "unavailable"),
        ],
    )

    assert f"cwd: {tmp_path} (ro)" in description
    assert f"  ro: {mounted}/*.md - available" in description
    assert str(missing) not in description


@pytest.mark.parametrize(
    ("display", "expected"),
    [
        ("~/notes/*.md", Path.home() / "notes"),
        ("~/Mail/{*.mbox,mail-index.sqlite}", Path.home() / "Mail"),
        ("~/code/README.md", Path.home() / "code/README.md"),
    ],
)
def test_mount_probe_path_uses_literal_display_prefix(display, expected) -> None:
    assert mcpserver.mount_probe_path(display) == expected
