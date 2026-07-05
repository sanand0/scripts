from __future__ import annotations

import json
import sys
from pathlib import Path

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
