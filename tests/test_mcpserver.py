from __future__ import annotations

import asyncio
import base64
import json
import sys
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import AudioContent, EmbeddedResource, ImageContent, TextContent

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mcpserver


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


def test_log_bash_command_includes_result_after_output(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")

    output, result = mcpserver.run_bash_command("printf ok", timeout_ms=1000)
    mcpserver.log_bash_command("printf ok", output, {"server_start_id": "start-test"}, result)

    [log_path] = tmp_path.glob("*.md")
    markdown = log_path.read_text()
    assert markdown.index("## Command") < markdown.index("## Request") < markdown.index("## Output") < markdown.index("## Result")
    result_json = json.loads(markdown.split("## Result", 1)[1].split("```", 2)[1])
    assert result_json["server_start_id"] == "start-test"
    assert result_json["exit_code"] == 0
    assert result_json["stdout_bytes"] == 2
    assert result_json["stderr_bytes"] == 0
    assert result_json["output_bytes_before_limits"] == 2
    assert result_json["output_bytes_after_limits"] == 2
    assert result_json["line_trim_count"] == 0
    assert result_json["total_truncation_omitted_bytes"] == 0
    assert "printf ok" in markdown


def test_run_bash_command_records_nonzero_and_timeout() -> None:
    output, result = mcpserver.run_bash_command("printf err >&2; exit 7", timeout_ms=1000)

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


def test_startup_record_is_compact_jsonl(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")
    monkeypatch.setattr(mcpserver, "tool_description_hash", lambda: "hash-test")
    monkeypatch.setattr(mcpserver, "git_state", lambda: {"commit": "abc123", "dirty": True})

    record = mcpserver.log_startup_record()

    [line] = (tmp_path / "startup.jsonl").read_text().splitlines()
    logged = json.loads(line)
    assert logged == record
    assert logged["server_start_id"] == "start-test"
    assert logged["pid"] > 0
    assert logged["cwd"]
    assert logged["git"] == {"commit": "abc123", "dirty": True}
    assert logged["tool_description_hash"] == "hash-test"


def test_request_close_log_excludes_sensitive_http_details(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(mcpserver, "LOG_DIR", tmp_path)
    monkeypatch.setattr(mcpserver, "SERVER_START_ID", "start-test")

    record = mcpserver.log_request_close(
        {
            "request_id": "req-1",
            "session_id": "sess-1",
            "method": "tools/call",
            "protocol_version": "2025-06-18",
            "http": {
                "path": "/mcp",
                "user_agent": "agent/1",
                "client": ["127.0.0.1", 1234],
                "headers": [{"name": "authorization", "value": "secret"}],
                "body": {"openai": "identifier"},
            },
            "duration_ms": 12.3,
            "result": "ok",
            "trace_id": "trace",
        }
    )

    [log_path] = tmp_path.glob("requests-*.jsonl")
    logged = json.loads(log_path.read_text())
    assert logged == record
    assert logged == {
        "server_start_id": "start-test",
        "timestamp": logged["timestamp"],
        "request_id": "req-1",
        "session_id": "sess-1",
        "mcp_method": "tools/call",
        "http_path": "/mcp",
        "user_agent": "agent/1",
        "protocol_version": "2025-06-18",
        "duration_ms": 12.3,
        "result": "ok",
    }
    serialized = json.dumps(logged)
    assert "secret" not in serialized
    assert "127.0.0.1" not in serialized
    assert "trace" not in serialized
    assert "openai" not in serialized


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


def test_read_returns_utf8_text_and_complete_metadata(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("Hello, αβ!", encoding="utf-8")

    result = mcpserver.read(str(path))

    assert result.structured_content == {
        "path": str(path.resolve()),
        "mime_type": "text/plain",
        "encoding": "utf-8",
        "size": path.stat().st_size,
        "offset": 0,
        "bytes_read": path.stat().st_size,
        "next_offset": None,
        "eof": True,
    }
    assert isinstance(result.content[0], TextContent)
    assert json.loads(result.content[0].text) == result.structured_content
    assert isinstance(result.content[1], TextContent)
    assert result.content[1].text == "Hello, αβ!"


def test_read_keeps_utf8_chunks_on_character_boundaries(tmp_path) -> None:
    path = tmp_path / "greek.txt"
    path.write_text("αβ", encoding="utf-8")

    first = mcpserver.read(str(path), limit=3)
    second = mcpserver.read(str(path), offset=first.structured_content["next_offset"], limit=3)

    assert first.content[1].text == "α"
    assert first.structured_content["bytes_read"] == 2
    assert first.structured_content["next_offset"] == 2
    assert first.structured_content["eof"] is False
    assert second.content[1].text == "β"
    assert second.structured_content["eof"] is True


@pytest.mark.parametrize(
    ("name", "data", "content_type", "mime_type"),
    [
        ("pixel.png", b"\x89PNG\r\n\x1a\ncontent", ImageContent, "image/png"),
        ("sound.mp3", b"ID3content", AudioContent, "audio/mpeg"),
        ("document.pdf", b"%PDF-1.7\ncontent", EmbeddedResource, "application/pdf"),
    ],
)
def test_read_returns_native_mcp_binary_content(tmp_path, name, data, content_type, mime_type) -> None:
    path = tmp_path / name
    path.write_bytes(data)

    result = mcpserver.read(str(path))

    payload = result.content[1]
    assert isinstance(payload, content_type)
    assert result.structured_content["mime_type"] == mime_type
    assert result.structured_content["encoding"] == "base64"
    if isinstance(payload, EmbeddedResource):
        assert payload.resource.mimeType == mime_type
        encoded = payload.resource.blob
    else:
        assert payload.mimeType == mime_type
        encoded = payload.data
    assert base64.b64decode(encoded) == data


def test_read_paginates_large_binary_without_silent_truncation(tmp_path) -> None:
    path = tmp_path / "large.pdf"
    path.write_bytes(b"0123456789")

    first = mcpserver.read(str(path), offset=2, limit=4)
    second = mcpserver.read(str(path), offset=first.structured_content["next_offset"], limit=4)

    assert first.structured_content["bytes_read"] == 4
    assert first.structured_content["next_offset"] == 6
    assert first.structured_content["eof"] is False
    assert first.content[1].resource.mimeType == "application/octet-stream"
    assert base64.b64decode(first.content[1].resource.blob) == b"2345"
    assert base64.b64decode(second.content[1].resource.blob) == b"6789"
    assert second.structured_content["eof"] is True


def test_read_transfers_binary_larger_than_bash_output_cap(tmp_path) -> None:
    data = b"\0\1" * (mcpserver.MAX_TOTAL_OUTPUT_BYTES // 2 + 1)
    path = tmp_path / "large.bin"
    path.write_bytes(data)

    result = mcpserver.read(str(path))

    assert result.structured_content["bytes_read"] > mcpserver.MAX_TOTAL_OUTPUT_BYTES
    assert result.structured_content["eof"] is True
    assert base64.b64decode(result.content[1].resource.blob) == data


def test_read_empty_and_unknown_utf8_files(tmp_path) -> None:
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    extensionless = tmp_path / "README"
    extensionless.write_text("plain text", encoding="utf-8")

    empty_result = mcpserver.read(str(empty))
    text_result = mcpserver.read(str(extensionless))

    assert empty_result.structured_content["bytes_read"] == 0
    assert empty_result.structured_content["eof"] is True
    assert base64.b64decode(empty_result.content[1].resource.blob) == b""
    assert text_result.structured_content["mime_type"] == "text/plain"
    assert text_result.content[1].text == "plain text"


def test_read_reports_invalid_arguments_and_filesystem_errors(tmp_path, monkeypatch) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content")

    with pytest.raises(ToolError, match="offset must be non-negative"):
        mcpserver.read(str(path), offset=-1)
    with pytest.raises(ToolError, match="limit must be between 1 and"):
        mcpserver.read(str(path), limit=mcpserver.MAX_READ_BYTES + 1)
    with pytest.raises(ToolError, match="File not found"):
        mcpserver.read(str(tmp_path / "missing.txt"))
    with pytest.raises(ToolError, match="Not a regular file"):
        mcpserver.read(str(tmp_path))

    original_open = Path.open

    def deny_open(self, *args, **kwargs):
        if self == path:
            raise PermissionError(13, "Permission denied", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(ToolError, match="Permission denied"):
        mcpserver.read(str(path))


def test_read_rejects_mid_character_offset(tmp_path) -> None:
    path = tmp_path / "greek.txt"
    path.write_text("αβ", encoding="utf-8")

    with pytest.raises(ToolError, match="UTF-8 character boundary"):
        mcpserver.read(str(path), offset=1, limit=2)

    with pytest.raises(ToolError, match="limit is too small for the next UTF-8 character"):
        mcpserver.read(str(path), limit=1)


def test_read_tool_is_registered_read_only_and_callable(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool("read", {"path": str(path)})
            return tools, result

    tools, result = asyncio.run(exercise_tool())
    read_tool = next(tool for tool in tools if tool.name == "read")
    assert read_tool.annotations.readOnlyHint is True
    assert read_tool.annotations.openWorldHint is False
    assert result.is_error is False
    assert result.structured_content["path"] == str(path.resolve())
    assert result.content[1].text == "hello"
