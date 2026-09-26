from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import sys
import threading
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


class BashContext:
    request_id = "test-request"

    async def info(self, message: str) -> None:
        pass

    async def warning(self, message: str) -> None:
        pass


def successful_bash_result() -> tuple[str, dict]:
    return "ok", {"stderr_bytes": 0, "exit_code": 0, "ok": True}


def test_http_app_uses_mcp2428_endpoint() -> None:
    app = mcpserver.mcp.http_app(path=mcpserver.MCP_PATH)

    assert [route.path for route in app.routes] == ["/mcp2428"]


def test_main_starts_http_server_without_cloudflare_token(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["mcpserver.py"])
    monkeypatch.setattr(mcpserver, "log_startup_record", lambda: {})
    monkeypatch.setattr(mcpserver.mcp, "run", lambda **kwargs: calls.append(kwargs))

    mcpserver.main()

    assert calls == [{
        "transport": "http",
        "port": 2428,
        "path": "/mcp2428",
        "stateless_http": True,
    }]


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


def test_finalize_output_persists_full_output_when_trimmed(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver.tempfile, "tempdir", str(tmp_path))
    original = (("x" * 1024) + "\n") * 600

    output, result = mcpserver.finalize_output(original, {})

    assert result["total_truncation_omitted_bytes"] > 0
    assert result["output_path"]
    assert Path(result["output_path"]).read_text() == original
    assert len(output.encode()) <= mcpserver.MAX_TOTAL_OUTPUT_BYTES


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


def test_run_bash_command_does_not_leak_mcpserver_uv_environment(monkeypatch) -> None:
    server_bin = str(Path(sys.executable).parent)
    monkeypatch.setenv("VIRTUAL_ENV", str(Path(sys.executable).parent.parent))
    monkeypatch.setenv("UV_RUN_RECURSION_DEPTH", "1")
    monkeypatch.setenv("PATH", f"{server_bin}:/usr/bin")

    output, result = mcpserver.run_bash_command(
        "env | grep -E '^(VIRTUAL_ENV|UV_RUN_RECURSION_DEPTH|PATH)=' || true",
        timeout_ms=1000,
    )

    assert result["exit_code"] == 0
    assert "VIRTUAL_ENV=" not in output
    assert "UV_RUN_RECURSION_DEPTH=" not in output
    assert server_bin not in output
    assert "PATH=/usr/bin" in output


def test_bash_returns_structured_nonzero_result_as_tool_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool(
                "bash",
                {"commands": "printf no >&2; exit 7", "cwd": str(tmp_path)},
                raise_on_error=False,
            )

    result = asyncio.run(exercise_tool())

    assert result.is_error is True
    assert "Return code: 7" in result.content[0].text
    assert result.structured_content["exit_code"] == 7
    assert result.structured_content["status"] == "failed"
    assert result.structured_content["ok"] is False
    assert result.structured_content["output"] == result.content[0].text
    assert result.structured_content["output_path"] is None
    assert result.structured_content["timed_out"] is False
    assert result.structured_content["error_code"] == "nonzero_exit"
    assert result.structured_content["retryable"] is False
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
    assert result.structured_content["status"] == "timeout"
    assert result.structured_content["ok"] is False
    assert result.structured_content["timed_out"] is True
    assert result.structured_content["error_code"] == "timeout"
    assert result.structured_content["retryable"] is False


def test_bash_runs_four_calls_concurrently(monkeypatch) -> None:
    barrier = threading.Barrier(4)
    threads = set()
    lock = threading.Lock()

    def run_bash_command(*args):
        with lock:
            threads.add(threading.get_ident())
        barrier.wait(timeout=5)
        return successful_bash_result()

    monkeypatch.setattr(mcpserver, "get_context", BashContext)
    monkeypatch.setattr(mcpserver, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcpserver, "run_bash_command", run_bash_command)

    async def exercise_tool():
        await asyncio.gather(*(mcpserver.bash(f"command {index}") for index in range(4)))

    asyncio.run(exercise_tool())

    assert len(threads) == 4


def test_bash_queues_fifth_call_and_never_exceeds_four(monkeypatch) -> None:
    four_started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    started = active = peak = 0

    def run_bash_command(*args):
        nonlocal started, active, peak
        with lock:
            started += 1
            active += 1
            peak = max(peak, active)
            if started == 4:
                four_started.set()
        try:
            assert release.wait(timeout=5)
            return successful_bash_result()
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(mcpserver, "get_context", BashContext)
    monkeypatch.setattr(mcpserver, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(mcpserver, "run_bash_command", run_bash_command)

    async def exercise_tool():
        tasks = [asyncio.create_task(mcpserver.bash(f"command {index}")) for index in range(5)]
        await asyncio.sleep(0)
        try:
            assert await asyncio.to_thread(four_started.wait, 5)
            with lock:
                assert started == active == peak == 4
            assert not any(task.done() for task in tasks)
        finally:
            release.set()
        await asyncio.gather(*tasks)

    asyncio.run(exercise_tool())

    assert started == 5
    assert peak == 4


def test_bash_invalid_input_is_structured_tool_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("bash", {"commands": " "}, raise_on_error=False)

    result = asyncio.run(exercise_tool())

    assert result.is_error is True
    assert result.structured_content["status"] == "error"
    assert result.structured_content["ok"] is False
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
    assert logged["stateless_http"] is True
    startup = capsys.readouterr().out
    assert startup.startswith("MCP HTTP mode: stateless\n")
    assert "mounted paths (rw = read-write, ro = read-only):\n" in startup


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
    assert "uv run context.py search QUERY" in bash_tool.description
    assert "Deep-read returned locators" in bash_tool.description
    assert "unfamiliar/version-sensitive CLI" in bash_tool.description
    assert "JSON vs JSONL" in bash_tool.description
    assert "project-native verification" in bash_tool.description
    assert "Prefer `read_file`/`read_files`, `list_directory`, `file_info`, `search`, and `edit_block`" in bash_tool.description
    assert "download_file" in bash_tool.description
    assert result.content[0].text.strip() == str(tmp_path)
    assert result.structured_content["output"].strip() == str(tmp_path)
    assert result.structured_content["status"] == "success"
    assert result.structured_content["ok"] is True
    assert result.structured_content["output_path"] is None


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

# --- semantic file/search tools ---

def test_read_file_is_one_based_bounded_and_resumable(tmp_path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("one\ntwo\nthree\nfour\n")
    result = mcpserver._read_file(str(path), start_line=2, line_count=2)
    assert result["content"] == "two\nthree\n"
    assert result["start_line"] == 2
    assert result["end_line"] == 3
    assert result["has_more"] is True
    assert result["next_start_line"] == 4


def test_read_files_keeps_partial_successes_and_limits_batch_size(tmp_path) -> None:
    good = tmp_path / "good.txt"
    good.write_text("hello\nworld\n")
    result = mcpserver._read_files([str(good), str(tmp_path / "missing.txt")], line_count=1)
    assert result["files"][0]["content"] == "hello\n"
    assert "error" in result["files"][1]
    with pytest.raises(ToolError, match="at most"):
        mcpserver._read_files([str(good)] * (mcpserver.MAX_READ_FILES + 1))


def test_list_directory_is_breadth_first_and_bounds_each_directory(tmp_path) -> None:
    for dirname in ("a", "b"):
        directory = tmp_path / dirname
        directory.mkdir()
        for index in range(8):
            (directory / f"{index}.txt").write_text(str(index))
    (tmp_path / "README.md").write_text("read me")
    result = mcpserver._list_directory(str(tmp_path), depth=2, max_entries=8, per_directory=3)
    paths = [entry["path"] for entry in result["entries"]]
    assert paths[:3] == ["README.md", "a/", "b/"]
    assert any(item["path"] == "a/" and item["omitted"] == 5 for item in result["omitted"])
    assert any(item["path"] == "b/" and item["omitted"] == 5 for item in result["omitted"])
    assert result["truncated"] is True


def test_file_info_reports_shape_without_hashing_by_default(tmp_path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("a\nb\n")
    result = mcpserver._file_info(str(path))
    assert result["type"] == "file"
    assert result["size"] == path.stat().st_size
    assert result["line_count"] == 2
    assert result["sha256"] is None


def test_edit_block_requires_exact_expected_count_and_returns_preview(tmp_path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("before\nold\nafter\nold\n")
    with pytest.raises(ToolError, match="Expected 1 occurrence"):
        mcpserver._edit_block(str(path), "old", "new")
    assert path.read_text() == "before\nold\nafter\nold\n"
    result = mcpserver._edit_block(str(path), "old", "new", expected_replacements=2)
    assert path.read_text() == "before\nnew\nafter\nnew\n"
    assert result["replacements"] == 2
    assert result["first_line"] == 2
    assert "before\nnew\nafter\nnew" in result["preview"]
    assert result["before_sha256"] != result["after_sha256"]


def test_search_returns_balanced_line_signal_for_narrow_result_set(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("needle one\nneedle two\nneedle three\n")
    (tmp_path / "b.txt").write_text("needle four\n")
    result = mcpserver._search("needle", str(tmp_path), max_results=4, max_files=5)
    assert result["broad"] is False
    assert result["matched_files"] == 2
    assert result["total_matches"] == 4
    assert {(Path(match["path"]).name, match["line"]) for match in result["matches"]} == {
        ("a.txt", 1), ("a.txt", 2), ("a.txt", 3), ("b.txt", 1)
    }


def test_search_summarizes_broad_results_instead_of_dumping_matches(tmp_path) -> None:
    for dirname in ("recent", "archive"):
        directory = tmp_path / dirname
        directory.mkdir()
        for index in range(6):
            (directory / f"{index}.md").write_text(f"needle {index}\n")
    result = mcpserver._search("needle", str(tmp_path), max_results=20, max_files=3)
    assert result["broad"] is True
    assert result["matched_files"] == 12
    assert result["matches"] == []
    assert {item["group"] for item in result["top_groups"][:2]} == {"archive", "recent"}
    assert len(result["sample_files"]) <= 3
    assert result["summary_is_sample"] is False


def test_semantic_tools_have_read_write_annotations() -> None:
    async def list_tools():
        async with Client(mcpserver.mcp) as client:
            return await client.list_tools()
    tools = {tool.name: tool for tool in asyncio.run(list_tools())}
    for name in ("read_file", "read_files", "list_directory", "file_info", "search"):
        assert tools[name].annotations.readOnlyHint is True
        assert tools[name].annotations.destructiveHint is False
        assert tools[name].annotations.openWorldHint is False
    assert tools["edit_block"].annotations.readOnlyHint is False
    assert tools["edit_block"].annotations.destructiveHint is True
    assert tools["edit_block"].annotations.openWorldHint is False
    assert "per_directory" not in tools["list_directory"].inputSchema["properties"]
    assert "max_files" not in tools["search"].inputSchema["properties"]



def test_search_caps_candidate_scan_and_marks_summary_as_sample(tmp_path) -> None:
    for index in range(mcpserver.SEARCH_CANDIDATE_CAP + 5):
        (tmp_path / f"{index:03}.txt").write_text("needle\n")
    result = mcpserver._search("needle", str(tmp_path))
    assert result["broad"] is True
    assert result["matched_files"] == mcpserver.SEARCH_CANDIDATE_CAP
    assert result["matched_files_is_lower_bound"] is True
    assert result["summary_is_sample"] is True
    assert "first 200" in result["hint"]


# --- reliability contracts ---

def test_server_instructions_are_returned_on_initialize() -> None:
    async def initialize():
        async with Client(mcpserver.mcp) as client:
            return client.initialize_result

    result = asyncio.run(initialize())

    assert result.instructions == mcpserver.SERVER_INSTRUCTIONS
    assert "Prefer read_file/read_files/search/list_directory/file_info" in result.instructions
    assert "Never automatically retry bash" in result.instructions


def test_read_file_tool_does_not_block_event_loop(tmp_path, monkeypatch) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello\n")
    started = threading.Event()
    release = threading.Event()
    original = mcpserver._read_file

    def slow_read(*args, **kwargs):
        started.set()
        assert release.wait(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(mcpserver, "_read_file", slow_read)

    async def exercise():
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, release.set)
        async with Client(mcpserver.mcp) as client:
            start = loop.time()
            result = await client.call_tool("read_file", {"path": str(path)})
            return loop.time() - start, result

    elapsed, result = asyncio.run(exercise())

    assert started.is_set()
    assert elapsed < 0.5
    assert result.structured_content["content"] == "hello\n"


def test_structured_tool_error_preserves_success_schema_and_classifies_missing_path(tmp_path) -> None:
    missing = tmp_path / "missing.txt"

    async def exercise():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("read_file", {"path": str(missing)}, raise_on_error=False)

    result = asyncio.run(exercise())

    assert result.is_error is True
    assert result.structured_content == {
        "ok": False,
        "error": {
            "code": "not_found",
            "retryable": False,
            "message": f"Path not found: {missing.resolve()}",
            "path": str(missing.resolve()),
            "suggestion": "Check the path or locate it with search/list_directory before retrying.",
        },
    }


def test_retry_transient_io_retries_only_known_transient_errors(monkeypatch) -> None:
    sleeps = []
    attempts = 0

    def transient_then_ok():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise BlockingIOError(11, "try again")
        return "ok"

    monkeypatch.setattr(mcpserver.time, "sleep", sleeps.append)

    assert mcpserver.retry_transient_io(transient_then_ok) == "ok"
    assert attempts == 3
    assert sleeps == list(mcpserver.TRANSIENT_RETRY_DELAYS)

    attempts = 0

    def denied():
        nonlocal attempts
        attempts += 1
        raise PermissionError(13, "permission denied")

    with pytest.raises(PermissionError):
        mcpserver.retry_transient_io(denied)
    assert attempts == 1


def test_read_file_retries_transient_os_error(tmp_path, monkeypatch) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello\n")
    original_open = Path.open
    attempts = 0

    def flaky_open(self, *args, **kwargs):
        nonlocal attempts
        if self == path.resolve() and attempts < 1:
            attempts += 1
            raise BlockingIOError(11, "try again", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", flaky_open)
    monkeypatch.setattr(mcpserver.time, "sleep", lambda _: None)

    result = mcpserver._read_file(str(path))

    assert result["content"] == "hello\n"
    assert attempts == 1


def test_permission_error_is_structured_and_not_retryable(tmp_path, monkeypatch) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("hello\n")
    original_open = Path.open
    attempts = 0

    def deny_open(self, *args, **kwargs):
        nonlocal attempts
        if self == path.resolve():
            attempts += 1
            raise PermissionError(13, "Permission denied", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)

    async def exercise():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("read_file", {"path": str(path)}, raise_on_error=False)

    result = asyncio.run(exercise())

    assert attempts == 1
    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "permission_denied"
    assert result.structured_content["error"]["retryable"] is False


def test_bash_cancellation_terminates_process_group(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "child.pid"
    monkeypatch.setattr(mcpserver, "get_context", BashContext)
    monkeypatch.setattr(mcpserver, "log_event", lambda *args, **kwargs: None)

    async def exercise():
        task = asyncio.create_task(
            mcpserver.bash(f"sleep 30 & echo $! > {pid_path}; wait", timeout_ms=30_000)
        )
        for _ in range(100):
            if pid_path.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_path.exists()
        child_pid = int(pid_path.read_text())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        for _ in range(100):
            try:
                Path(f"/proc/{child_pid}").stat()
            except FileNotFoundError:
                return
            await asyncio.sleep(0.01)
        pytest.fail(f"cancelled bash child {child_pid} is still running")

    asyncio.run(exercise())


def test_truncate_middle_preserves_head_tail_and_reports_omission() -> None:
    text = "HEAD-" + ("x" * 5000) + "-TAIL"

    result = mcpserver.truncate_middle(text, 200)

    assert len(result) <= 200
    assert result.startswith("HEAD-")
    assert result.endswith("-TAIL")
    assert "chars omitted" in result


def test_tool_call_audit_logs_full_request_response_and_truncates_console(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(mcpserver, "CONSOLE_RESPONSE_CHARS", 300)
    path = tmp_path / "long.txt"
    content = "START-" + ("x" * 3000) + "-END\n"
    path.write_text(content)

    async def exercise():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool("read_file", {"path": str(path), "line_count": 1})

    result = asyncio.run(exercise())
    assert result.structured_content["content"] == content

    console = capsys.readouterr().err
    assert "▶ read_file" in console
    assert str(path) in console
    assert "✓ read_file" in console
    assert "chars omitted" in console
    assert "START-" in console and "-END" in console
    assert content not in console

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "events.jsonl").read_text().splitlines()
    ]
    [audit] = [event for event in events if event["operation"] == "tool_call"]
    assert audit["tool"] == "read_file"
    assert audit["arguments"] == {"path": str(path), "line_count": 1}
    assert audit["response"]["structured_content"]["content"] == content
    assert audit["is_error"] is False

    [markdown_path] = (tmp_path / "logs" / "tool-calls").glob("????-??/*.md")
    markdown = markdown_path.read_text()
    assert "## Arguments" in markdown
    assert str(path) in markdown
    assert "## Response" in markdown
    assert content.rstrip("\n") in markdown


def test_tool_call_audit_logs_structured_error(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path / "logs")
    missing = tmp_path / "missing.txt"

    async def exercise():
        async with Client(mcpserver.mcp) as client:
            return await client.call_tool(
                "read_file", {"path": str(missing)}, raise_on_error=False
            )

    result = asyncio.run(exercise())
    assert result.is_error is True

    console = capsys.readouterr().err
    assert "✗ read_file" in console
    assert "• not_found • Path not found:" in console

    events = [
        json.loads(line)
        for line in (tmp_path / "logs" / "events.jsonl").read_text().splitlines()
    ]
    [audit] = [event for event in events if event["operation"] == "tool_call"]
    assert audit["is_error"] is True
    assert audit["response"]["structured_content"]["error"]["code"] == "not_found"


def test_main_can_opt_back_into_stateful_http(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("MCPSERVER_STATEFUL_HTTP", "1")
    monkeypatch.setattr(sys, "argv", ["mcpserver.py"])
    monkeypatch.setattr(mcpserver, "log_startup_record", lambda: {})
    monkeypatch.setattr(mcpserver.mcp, "run", lambda **kwargs: calls.append(kwargs))

    mcpserver.main()

    assert calls == [{"transport": "http", "port": 2428, "path": "/mcp2428"}]


def test_console_color_uses_ansi_only_on_tty(monkeypatch) -> None:
    class Tty:
        def isatty(self):
            return True

    monkeypatch.setattr(mcpserver.sys, "stderr", Tty())
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert mcpserver.console_color("hello", "green") == "\x1b[32mhello\x1b[0m"

    monkeypatch.setenv("NO_COLOR", "1")
    assert mcpserver.console_color("hello", "green") == "hello"


def test_tool_console_formats_file_info_for_rapid_scanning() -> None:
    request = mcpserver.format_tool_request(
        "file_info", {"path": "/home/vscode/code/demo/report.md", "sha256": False}
    )
    response = mcpserver.format_tool_response(
        "file_info",
        {
            "is_error": False,
            "structured_content": {
                "path": "/home/vscode/code/demo/report.md",
                "type": "file",
                "size": 1_234_567,
                "modified": "2026-09-26T02:37:12+00:00",
                "line_count": 6146,
                "mime_type": "text/markdown",
                "access": "rw",
                "sha256": None,
            },
        },
        12.3,
        False,
    )

    assert request == ["~/code/demo/report.md"]
    assert response == [
        "file_info 12.3 ms • 1.2 MB • 6,146 lines • modified 26 Sep 2026 10:37"
    ]


def test_tool_console_formats_content_tools_with_compact_preview() -> None:
    read_request = mcpserver.format_tool_request(
        "read_file",
        {"path": "/home/vscode/code/demo/a.py", "start_line": 21, "line_count": 50},
    )
    read_response = mcpserver.format_tool_response(
        "read_file",
        {
            "is_error": False,
            "structured_content": {
                "path": "/home/vscode/code/demo/a.py",
                "start_line": 21,
                "end_line": 70,
                "line_count": 50,
                "next_start_line": 71,
                "byte_limited": False,
                "content": "def one():\n    pass\n",
            },
        },
        4.2,
        False,
    )

    assert read_request == ["~/code/demo/a.py • lines 21–70"]
    assert read_response[0] == "read_file 4.2 ms • 50 lines • 20 B • more→71"
    assert read_response[1] == "def one():\n    pass\n"

    search_response = mcpserver.format_tool_response(
        "search",
        {
            "is_error": False,
            "structured_content": {
                "broad": False,
                "matched_files": 2,
                "total_matches": 3,
                "matches": [
                    {"path": "/home/vscode/code/a.py", "line": 10, "text": "needle one"},
                    {"path": "/home/vscode/code/b.py", "line": 20, "text": "needle two"},
                ],
            },
        },
        8.5,
        False,
    )
    assert search_response[0] == "search 8.5 ms • 3 matches in 2 files • showing 2"
    assert "~/code/a.py:10  needle one" in search_response[1]


def test_tool_console_formats_edit_and_errors_compactly() -> None:
    request = mcpserver.format_tool_request(
        "edit_block",
        {
            "path": "/home/vscode/code/a.py",
            "old_string": "old\ntext",
            "new_string": "new\ntext",
            "expected_replacements": 1,
        },
    )
    assert request == [
        "~/code/a.py • expect 1 replacement",
        "old:\nold\ntext",
        "new:\nnew\ntext",
    ]

    error = mcpserver.format_tool_response(
        "read_file",
        {
            "is_error": True,
            "structured_content": {
                "ok": False,
                "error": {
                    "code": "not_found",
                    "retryable": False,
                    "message": "Path not found: /tmp/missing",
                    "suggestion": "Check the path.",
                },
            },
        },
        1.1,
        True,
    )
    assert error == ["read_file 1.1 ms • not_found • Path not found: /tmp/missing"]


def test_stateless_http_is_default_with_stateful_rollback(monkeypatch) -> None:
    monkeypatch.delenv("MCPSERVER_STATELESS_HTTP", raising=False)
    monkeypatch.delenv("MCPSERVER_STATEFUL_HTTP", raising=False)
    assert mcpserver.stateless_http_enabled() is True

    monkeypatch.setenv("MCPSERVER_STATEFUL_HTTP", "1")
    assert mcpserver.stateless_http_enabled() is False


def test_console_read_previews_truncate_middle_and_keep_file_headers(monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "CONSOLE_RESPONSE_CHARS", 240)
    long_content = "HEAD\n" + ("x" * 500) + "\nTAIL\n"

    single = mcpserver.format_tool_response(
        "read_file",
        {
            "is_error": False,
            "structured_content": {
                "path": "/home/vscode/code/a.txt",
                "line_count": 3,
                "next_start_line": None,
                "byte_limited": False,
                "content": long_content,
            },
        },
        1.0,
        False,
    )
    assert single[1].startswith("HEAD")
    assert single[1].endswith("TAIL\n")
    assert "chars omitted" in single[1]

    multi = mcpserver.format_tool_response(
        "read_files",
        {
            "is_error": False,
            "structured_content": {
                "files": [
                    {
                        "path": "/home/vscode/code/a.txt",
                        "start_line": 1,
                        "end_line": 3,
                        "line_count": 3,
                        "content": long_content,
                    },
                    {
                        "path": "/home/vscode/code/b.txt",
                        "start_line": 10,
                        "end_line": 12,
                        "line_count": 3,
                        "content": long_content,
                    },
                ]
            },
        },
        2.0,
        False,
    )
    preview = multi[1]
    assert "━━ ~/code/a.txt • lines 1–3 ━━" in preview
    assert "━━ ~/code/b.txt • lines 10–12 ━━" in preview
    assert preview.count("chars omitted") == 2


def test_console_list_directory_truncates_middle_by_entries() -> None:
    entries = [{"path": f"item-{index:02}.txt"} for index in range(20)]
    response = mcpserver.format_tool_response(
        "list_directory",
        {
            "is_error": False,
            "structured_content": {
                "entries": entries,
                "depth": 1,
                "truncated": False,
            },
        },
        3.0,
        False,
    )

    preview = response[1]
    assert "item-00.txt" in preview
    assert "item-05.txt" in preview
    assert "… 8 entries omitted …" in preview
    assert "item-14.txt" in preview
    assert "item-19.txt" in preview
    assert "item-06.txt" not in preview
