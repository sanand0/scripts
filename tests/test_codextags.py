from __future__ import annotations

import csv
from pathlib import Path
import sys

import orjson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codextags import update_tags


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for record in records:
            handle.write(orjson.dumps(record))
            handle.write(b"\n")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload))


def _read_rows(csv_path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = {row["session_key"]: row for row in reader}
    return headers, rows


def _write_rows(csv_path: Path, headers: list[str], rows: dict[str, dict[str, str]]) -> None:
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for key in sorted(rows):
            writer.writerow(rows[key])


def _seed_sessions(root: Path) -> tuple[str, str]:
    jsonl_path = root / "2026/03/03/rollout-sample.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            {
                "timestamp": "2026-03-03T08:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "session-jsonl",
                    "timestamp": "2026-03-03T08:00:00Z",
                    "cwd": "/tmp/demo",
                    "cli_version": "0.1.0",
                    "model_provider": "openai",
                    "source": {"subagent": {"depth": 1}},
                },
            },
            {
                "timestamp": "2026-03-03T08:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "# AGENTS.md instructions for /tmp/demo\n\n"
                                "<INSTRUCTIONS>\n"
                                "Available tools:\n\n"
                                "fd, find\n"
                                "rg, grep\n\n"
                                "## Skills\n"
                                "- code: ALWAYS follow this style when writing code\n"
                                "</INSTRUCTIONS>\n\n"
                                "<environment_context>\n"
                                "  <cwd>/tmp/demo</cwd>\n"
                                "</environment_context>\n\n"
                                "Please update PLAN.md, implement a new feature, and add tests for src/app.py."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-03-03T08:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c1",
                    "arguments": "{\"cmd\":\"sed -n '1,80p' /home/vscode/code/scripts/agents/data-story/SKILL.md && uv run tool.py\"}",
                },
            },
            {
                "timestamp": "2026-03-03T08:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "{\"output\":\"ok\",\"metadata\":{\"exit_code\":0}}",
                },
            },
            {
                "timestamp": "2026-03-03T08:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "name": "apply_patch",
                    "call_id": "c2",
                    "input": "*** Begin Patch\n*** Update File: src/app.py\n@@\n-print('old')\n+print('new')\n*** End Patch\n",
                },
            },
            {
                "timestamp": "2026-03-03T08:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "c2",
                    "output": "{\"output\":\"ok\",\"metadata\":{\"exit_code\":0}}",
                },
            },
            {
                "timestamp": "2026-03-03T08:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "playwright__browser_navigate",
                    "call_id": "c3",
                    "arguments": "{\"url\":\"https://example.com\"}",
                },
            },
            {
                "timestamp": "2026-03-03T08:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c3",
                    "output": "{\"output\":\"ok\",\"metadata\":{\"exit_code\":0}}",
                },
            },
        ],
    )

    legacy_jsonl_path = root / "2025/04/17/rollout-legacy.jsonl"
    _write_jsonl(
        legacy_jsonl_path,
        [
            {
                "timestamp": "2025-04-17T00:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": "session-jsonl-legacy",
                    "timestamp": "2025-04-17T00:00:00Z",
                    "cwd": "/tmp/legacy",
                    "model_provider": "openai",
                },
            },
            {
                "timestamp": "2025-04-17T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Fix failing tests in parser"}],
                },
            },
            {
                "timestamp": "2025-04-17T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "legacy-call",
                    "arguments": "{\"command\":[\"bash\",\"-lc\",\"pytest -q | tee out.txt\"]}",
                },
            },
            {
                "timestamp": "2025-04-17T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "legacy-call",
                    "output": "{\"output\":\"failed\",\"metadata\":{\"exit_code\":1}}",
                },
            },
        ],
    )

    json_path = root / "rollout-old-format.json"
    _write_json(
        json_path,
        {
            "session": {
                "timestamp": "2025-04-17T00:00:00Z",
                "id": "old-format-session",
                "instructions": "",
            },
            "items": [
                {
                    "id": "m1",
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Fix failing tests in parser"}],
                    "timestamp": "2025-04-17T00:00:01Z",
                },
                {
                    "id": "f1",
                    "type": "function_call",
                    "name": "shell",
                    "call_id": "legacy-call",
                    "arguments": "{\"command\":[\"bash\",\"-lc\",\"pytest -q\"]}",
                    "timestamp": "2025-04-17T00:00:02Z",
                },
                {
                    "id": "o1",
                    "type": "function_call_output",
                    "call_id": "legacy-call",
                    "output": "{\"output\":\"failed\",\"metadata\":{\"exit_code\":1}}",
                    "timestamp": "2025-04-17T00:00:03Z",
                },
            ],
        },
    )

    return "2026/03/03/rollout-sample.jsonl", "2025/04/17/rollout-legacy.jsonl"


def test_incremental_update_and_idempotency(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    sample_key, legacy_key = _seed_sessions(sessions_root)
    tags_csv = sessions_root / "tags.csv"

    summary = update_tags(sessions_root=sessions_root, tags_csv=tags_csv, jobs=1)
    assert summary.total_sessions == 2
    assert summary.processed_sessions == 2
    assert summary.skipped_sessions == 0

    _, rows = _read_rows(tags_csv)
    assert set(rows) == {sample_key, legacy_key}
    assert rows[sample_key]["feature_apply_patch"] == "1"
    assert rows[sample_key]["files_edited_count"] == "1"
    assert rows[sample_key]["workflow_mode"] == "test_improvement"
    assert rows[sample_key]["prompt_has_acceptance_criteria"] == "1"
    assert rows[sample_key]["prompt_has_plans_md"] == "1"
    assert rows[sample_key]["feature_web"] == "1"
    assert "available tools" not in rows[sample_key]["objective_preview"].lower()
    assert rows[sample_key]["objective_preview"].startswith("Please update PLAN.md")
    assert rows[sample_key]["skill_count"] == "1"
    assert rows[sample_key]["skills_used"] == "data-story"
    assert "sed" in rows[sample_key]["executables_used"]
    assert "uv" in rows[sample_key]["executables_used"]
    assert rows[legacy_key]["tool_failure_count"] == "1"
    assert rows[legacy_key]["has_tool_failures"] == "1"
    assert rows[legacy_key]["verification_command_count"] == "1"
    assert rows[legacy_key]["test_command_count"] == "1"
    assert rows[legacy_key]["shell_error_rate"] == "1.0000"
    assert "pytest" in rows[legacy_key]["executables_used"]
    assert "tee" in rows[legacy_key]["executables_used"]

    rerun = update_tags(sessions_root=sessions_root, tags_csv=tags_csv, jobs=1)
    assert rerun.processed_sessions == 0
    assert rerun.skipped_sessions == 2


def test_missing_column_fill_and_force_recompute(tmp_path: Path) -> None:
    sessions_root = tmp_path / "sessions"
    _, legacy_key = _seed_sessions(sessions_root)
    tags_csv = sessions_root / "tags.csv"

    update_tags(sessions_root=sessions_root, tags_csv=tags_csv, jobs=1)
    headers, rows = _read_rows(tags_csv)

    rows[legacy_key]["intent_tags"] = "manual-tag"
    rows[legacy_key]["objective_preview"] = ""
    rows[legacy_key]["workflow_mode"] = ""
    _write_rows(tags_csv, headers, rows)

    fill_missing = update_tags(sessions_root=sessions_root, tags_csv=tags_csv, jobs=1)
    assert fill_missing.processed_sessions == 1

    _, rows_after_fill = _read_rows(tags_csv)
    assert rows_after_fill[legacy_key]["intent_tags"] == "manual-tag"
    assert rows_after_fill[legacy_key]["objective_preview"] != ""
    assert rows_after_fill[legacy_key]["workflow_mode"] == "bugfix_debug"

    force_summary = update_tags(sessions_root=sessions_root, tags_csv=tags_csv, force=True, jobs=1)
    assert force_summary.processed_sessions == 2

    _, rows_after_force = _read_rows(tags_csv)
    assert rows_after_force[legacy_key]["intent_tags"] != "manual-tag"
