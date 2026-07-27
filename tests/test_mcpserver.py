from __future__ import annotations

import asyncio
import base64
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


def test_startup_record_is_compact_jsonl_and_prints_mounts(tmp_path, monkeypatch, capsys) -> None:
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
    assert capsys.readouterr().out.startswith("mounted paths (rw = read-write, ro = read-only):\n")


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


def test_download_file_returns_complete_utf8_embedded_resource(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("Hello, αβ!", encoding="utf-8")

    result = mcpserver.download_file(str(path))

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

    result = mcpserver.download_file(str(path))

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

    result = mcpserver.download_file(str(path))

    assert result.structured_content["bytes_read"] > mcpserver.MAX_TOTAL_OUTPUT_BYTES
    assert base64.b64decode(result.content[1].resource.blob) == data


def test_download_file_treats_invalid_utf8_text_as_blob(tmp_path) -> None:
    path = tmp_path / "invalid.txt"
    path.write_bytes(b"\xff")

    result = mcpserver.download_file(str(path))

    assert isinstance(result.content[1].resource, BlobResourceContents)
    assert result.content[1].resource.mimeType == "text/plain"
    assert base64.b64decode(result.content[1].resource.blob) == b"\xff"


def test_download_file_empty_and_unknown_utf8_files(tmp_path) -> None:
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")
    extensionless = tmp_path / "README"
    extensionless.write_text("plain text", encoding="utf-8")

    empty_result = mcpserver.download_file(str(empty))
    text_result = mcpserver.download_file(str(extensionless))

    assert empty_result.structured_content["bytes_read"] == 0
    assert base64.b64decode(empty_result.content[1].resource.blob) == b""
    assert text_result.structured_content["mime_type"] == "text/plain"
    assert text_result.content[1].resource.text == "plain text"


def test_download_file_reports_filesystem_errors(tmp_path, monkeypatch) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content")

    with pytest.raises(ToolError, match="File not found"):
        mcpserver.download_file(str(tmp_path / "missing.txt"))
    with pytest.raises(ToolError, match="Not a regular file"):
        mcpserver.download_file(str(tmp_path))

    original_open = Path.open

    def deny_open(self, *args, **kwargs):
        if self == path:
            raise PermissionError(13, "Permission denied", str(self))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_open)
    with pytest.raises(ToolError, match="Permission denied"):
        mcpserver.download_file(str(path))


def test_download_file_tool_is_registered_read_only_and_callable(tmp_path) -> None:
    path = tmp_path / "hello.txt"
    path.write_text("hello")

    async def exercise_tool():
        async with Client(mcpserver.mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool("download_file", {"path": str(path)})
            return tools, result

    tools, result = asyncio.run(exercise_tool())
    download_tool = next(tool for tool in tools if tool.name == "download_file")
    assert all(tool.name != "read" for tool in tools)
    assert download_tool.annotations.readOnlyHint is True
    assert download_tool.annotations.openWorldHint is False
    assert result.is_error is False
    assert result.structured_content["path"] == str(path.resolve())
    assert result.content[1].resource.text == "hello"


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
