from __future__ import annotations

import json
from pathlib import Path
import sys

from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skilluse import _normalize_skill_target, build_app


RUNNER = CliRunner()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row))
            handle.write("\n")


def test_skilluse_detects_reads_across_agents(tmp_path: Path) -> None:
    agents_root = tmp_path / "home" / "user" / "code" / "scripts" / "agents"
    plan_skill = agents_root / "plan" / "SKILL.md"
    data_skill = agents_root / "data-story" / "SKILL.md"
    plan_skill.parent.mkdir(parents=True, exist_ok=True)
    data_skill.parent.mkdir(parents=True, exist_ok=True)
    plan_skill.write_text("plan\n", encoding="utf-8")
    data_skill.write_text("story\n", encoding="utf-8")

    codex_root = tmp_path / "codex"
    _write_jsonl(
        codex_root / "sessions" / "2026" / "03" / "13" / "rollout-test.jsonl",
        [
            {
                "timestamp": "2026-03-13T08:00:00Z",
                "type": "session_meta",
                "payload": {"id": "codex-session"},
            },
            {
                "timestamp": "2026-03-13T08:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c1",
                    "arguments": json.dumps(
                        {"cmd": f"sed -n '1,20p' {plan_skill}", "workdir": str(tmp_path)}
                    ),
                },
            },
            {
                "timestamp": "2026-03-13T08:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Process exited with code 0\nOutput:\nname: plan\n",
                },
            },
            {
                "timestamp": "2026-03-13T08:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c2",
                    "arguments": json.dumps(
                        {"cmd": f"ls -lh {data_skill}", "workdir": str(tmp_path)}
                    ),
                },
            },
            {
                "timestamp": "2026-03-13T08:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c2",
                    "output": "Process exited with code 0\n",
                },
            },
        ],
    )

    claude_root = tmp_path / "claude-projects"
    _write_jsonl(
        claude_root / "demo" / "session.jsonl",
        [
            {
                "timestamp": "2026-03-14T08:00:00Z",
                "sessionId": "claude-session",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "read-1",
                            "name": "Read",
                            "input": {"file_path": str(data_skill)},
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-14T08:00:01Z",
                "sessionId": "claude-session",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "read-1",
                            "content": "name: data-story",
                            "is_error": False,
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-14T08:00:02Z",
                "sessionId": "claude-session",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "read-2",
                            "name": "Bash",
                            "input": {"command": f"ls -lh {plan_skill}", "description": "List file"},
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-14T08:00:03Z",
                "sessionId": "claude-session",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "read-2",
                            "content": "ok",
                            "is_error": False,
                        }
                    ]
                },
            },
        ],
    )

    copilot_root = tmp_path / "copilot-state"
    _write_jsonl(
        copilot_root / "copilot-session" / "events.jsonl",
        [
            {
                "timestamp": "2026-03-15T08:00:00Z",
                "type": "skill.invoked",
                "data": {"path": str(plan_skill), "name": "plan"},
            },
            {
                "timestamp": "2026-03-15T08:00:01Z",
                "type": "tool.execution_start",
                "data": {
                    "toolCallId": "copilot-1",
                    "toolName": "bash",
                    "arguments": {"command": f"cat {data_skill}"},
                },
            },
            {
                "timestamp": "2026-03-15T08:00:02Z",
                "type": "tool.execution_complete",
                "data": {"toolCallId": "copilot-1", "success": True},
            },
        ],
    )

    result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "json",
            "--codex-root",
            str(codex_root),
            "--claude-root",
            str(claude_root),
            "--copilot-root",
            str(copilot_root),
            "--agents-root",
            str(agents_root),
        ],
    )

    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert {tuple(sorted(row.items())) for row in rows} == {
        tuple(
            sorted(
                {
                    "agent": "copilot",
                    "session_date": "15 Mar 2026",
                    "skill": "plan",
                    "session_id": "copilot-session",
                    "timestamp": "2026-03-15T08:00:00Z",
                }.items()
            )
        ),
        tuple(
            sorted(
                {
                    "agent": "copilot",
                    "session_date": "15 Mar 2026",
                    "skill": "data-story",
                    "session_id": "copilot-session",
                    "timestamp": "2026-03-15T08:00:01Z",
                }.items()
            )
        ),
        tuple(
            sorted(
                {
                    "agent": "claude",
                    "session_date": "14 Mar 2026",
                    "skill": "data-story",
                    "session_id": "claude-session",
                    "timestamp": "2026-03-14T08:00:00Z",
                }.items()
            )
        ),
        tuple(
            sorted(
                {
                    "agent": "codex",
                    "session_date": "13 Mar 2026",
                    "skill": "plan",
                    "session_id": "codex-session",
                    "timestamp": "2026-03-13T08:00:01Z",
                }.items()
            )
        ),
    }


def test_skilluse_supports_absolute_paths_and_describe(tmp_path: Path) -> None:
    copilot_root = tmp_path / "copilot"
    external_skill = tmp_path / "skills" / "custom" / "SKILL.md"
    external_skill.parent.mkdir(parents=True, exist_ok=True)
    external_skill.write_text("custom\n", encoding="utf-8")
    _write_jsonl(
        copilot_root / "session-1" / "events.jsonl",
        [
            {
                "timestamp": "2026-03-16T08:00:00Z",
                "type": "skill.invoked",
                "data": {"path": str(external_skill), "name": "custom"},
            }
        ],
    )

    describe = RUNNER.invoke(build_app(), ["--describe"])
    assert describe.exit_code == 0, describe.stdout
    assert '"name": "skilluse"' in describe.stdout

    result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "text",
            "--agent",
            "copilot",
            "--copilot-root",
            str(copilot_root),
            "--agents-root",
            str(tmp_path / "home" / "user" / "code" / "scripts" / "agents"),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert result.stdout.splitlines() == [
        "agent\tdate\tskill\tsession_id",
        "copilot\t16 Mar 2026\tcustom\tsession-1",
    ]


def test_skilluse_normalizes_agents_paths_across_home_directories() -> None:
    sanand_agents = Path("/home/sanand/code/scripts/agents")
    vscode_skill = Path("/home/vscode/code/scripts/agents/plan/SKILL.md")
    assert _normalize_skill_target(str(vscode_skill), sanand_agents) == "plan"

    vscode_agents = Path("/home/vscode/code/scripts/agents")
    sanand_skill = Path("/home/sanand/code/scripts/agents/data-story/SKILL.md")
    assert _normalize_skill_target(str(sanand_skill), vscode_agents) == "data-story"


def test_skilluse_filters_by_skill_glob(tmp_path: Path) -> None:
    agents_root = tmp_path / "home" / "user" / "code" / "scripts" / "agents"
    agent_skill = agents_root / "agent-friendly-cli" / "SKILL.md"
    plan_skill = agents_root / "plan" / "SKILL.md"
    agent_skill.parent.mkdir(parents=True, exist_ok=True)
    plan_skill.parent.mkdir(parents=True, exist_ok=True)
    agent_skill.write_text("agent\n", encoding="utf-8")
    plan_skill.write_text("plan\n", encoding="utf-8")

    copilot_root = tmp_path / "copilot"
    _write_jsonl(
        copilot_root / "session-1" / "events.jsonl",
        [
            {
                "timestamp": "2026-03-16T08:00:00Z",
                "type": "skill.invoked",
                "data": {"path": str(agent_skill), "name": "agent-friendly-cli"},
            },
            {
                "timestamp": "2026-03-16T08:00:01Z",
                "type": "skill.invoked",
                "data": {"path": str(plan_skill), "name": "plan"},
            },
        ],
    )

    result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "text",
            "--agent",
            "copilot",
            "--skill",
            "agent-*",
            "--copilot-root",
            str(copilot_root),
            "--agents-root",
            str(agents_root),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert result.stdout.splitlines() == [
        "agent\tdate\tskill\tsession_id",
        "copilot\t16 Mar 2026\tagent-friendly-cli\tsession-1",
    ]


def test_skilluse_streams_newest_codex_files_first(tmp_path: Path) -> None:
    agents_root = tmp_path / "home" / "user" / "code" / "scripts" / "agents"
    plan_skill = agents_root / "plan" / "SKILL.md"
    plan_skill.parent.mkdir(parents=True, exist_ok=True)
    plan_skill.write_text("plan\n", encoding="utf-8")

    codex_root = tmp_path / "codex"
    _write_jsonl(
        codex_root / "sessions" / "2026" / "03" / "13" / "older.jsonl",
        [
            {
                "timestamp": "2026-03-13T08:00:01Z",
                "type": "session_meta",
                "payload": {"id": "older-session"},
            },
            {
                "timestamp": "2026-03-13T08:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c1",
                    "arguments": json.dumps({"cmd": f"cat {plan_skill}"}),
                },
            },
            {
                "timestamp": "2026-03-13T08:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Process exited with code 0\n",
                },
            },
        ],
    )
    _write_jsonl(
        codex_root / "sessions" / "2026" / "03" / "14" / "newer.jsonl",
        [
            {
                "timestamp": "2026-03-14T08:00:01Z",
                "type": "session_meta",
                "payload": {"id": "newer-session"},
            },
            {
                "timestamp": "2026-03-14T08:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c1",
                    "arguments": json.dumps({"cmd": f"cat {plan_skill}"}),
                },
            },
            {
                "timestamp": "2026-03-14T08:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Process exited with code 0\n",
                },
            },
        ],
    )

    result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "text",
            "--agent",
            "codex",
            "--codex-root",
            str(codex_root),
            "--agents-root",
            str(agents_root),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert result.stdout.splitlines() == [
        "agent\tdate\tskill\tsession_id",
        "codex\t14 Mar 2026\tplan\tnewer-session",
        "codex\t13 Mar 2026\tplan\tolder-session",
    ]


def test_skilluse_detects_claude_skill_tool_launches(tmp_path: Path) -> None:
    home = tmp_path / "home" / "user"
    agents_root = home / "code" / "scripts" / "agents"
    design_skill = agents_root / "design" / "SKILL.md"
    local_skill = home / "code" / "talks" / ".claude" / "skills" / "talk-story" / "SKILL.md"
    design_skill.parent.mkdir(parents=True, exist_ok=True)
    local_skill.parent.mkdir(parents=True, exist_ok=True)
    design_skill.write_text("design\n", encoding="utf-8")
    local_skill.write_text("talk story\n", encoding="utf-8")

    claude_root = home / ".claude" / "projects"
    _write_jsonl(
        claude_root / "demo" / "session.jsonl",
        [
            {
                "timestamp": "2026-03-17T08:00:00Z",
                "sessionId": "claude-session",
                "cwd": str(home / "code" / "talks"),
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "skill-1",
                            "name": "Skill",
                            "input": {"skill": "design"},
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-17T08:00:01Z",
                "sessionId": "claude-session",
                "cwd": str(home / "code" / "talks"),
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "skill-1",
                            "content": "Launching skill: design",
                            "is_error": False,
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-17T08:00:02Z",
                "sessionId": "claude-session",
                "cwd": str(home / "code" / "talks"),
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "skill-2",
                            "name": "Skill",
                            "input": {"skill": "talk-story"},
                        }
                    ]
                },
            },
            {
                "timestamp": "2026-03-17T08:00:03Z",
                "sessionId": "claude-session",
                "cwd": str(home / "code" / "talks"),
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "skill-2",
                            "content": "Launching skill: talk-story",
                            "is_error": False,
                        }
                    ]
                },
            },
        ],
    )

    result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "json",
            "--agent",
            "claude",
            "--claude-root",
            str(claude_root),
            "--agents-root",
            str(agents_root),
        ],
        env={"HOME": str(home)},
    )

    assert result.exit_code == 0, result.stdout
    rows = json.loads(result.stdout)
    assert {row["skill"] for row in rows} == {
        "design",
        "talk-story",
    }


def test_skilluse_agent_filter_and_default_order(tmp_path: Path) -> None:
    agents_root = tmp_path / "home" / "user" / "code" / "scripts" / "agents"
    plan_skill = agents_root / "plan" / "SKILL.md"
    design_skill = agents_root / "design" / "SKILL.md"
    plan_skill.parent.mkdir(parents=True, exist_ok=True)
    design_skill.parent.mkdir(parents=True, exist_ok=True)
    plan_skill.write_text("plan\n", encoding="utf-8")
    design_skill.write_text("design\n", encoding="utf-8")

    codex_root = tmp_path / "codex"
    _write_jsonl(
        codex_root / "sessions" / "2026" / "03" / "13" / "codex.jsonl",
        [
            {"timestamp": "2026-03-13T08:00:00Z", "type": "session_meta", "payload": {"id": "codex-session"}},
            {
                "timestamp": "2026-03-13T08:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "c1",
                    "arguments": json.dumps({"cmd": f"cat {plan_skill}"}),
                },
            },
            {
                "timestamp": "2026-03-13T08:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Process exited with code 0\n",
                },
            },
        ],
    )

    claude_root = tmp_path / "claude-projects"
    _write_jsonl(
        claude_root / "demo" / "session.jsonl",
        [
            {
                "timestamp": "2026-03-14T08:00:00Z",
                "sessionId": "claude-session",
                "cwd": str(tmp_path / "home" / "user" / "code" / "talks"),
                "message": {
                    "content": [
                        {"type": "tool_use", "id": "c1", "name": "Skill", "input": {"skill": "design"}}
                    ]
                },
            },
            {
                "timestamp": "2026-03-14T08:00:01Z",
                "sessionId": "claude-session",
                "cwd": str(tmp_path / "home" / "user" / "code" / "talks"),
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "c1", "content": "Launching skill: design", "is_error": False}
                    ]
                },
            },
        ],
    )

    copilot_root = tmp_path / "copilot-state"
    _write_jsonl(
        copilot_root / "copilot-session" / "events.jsonl",
        [
            {
                "timestamp": "2026-03-15T08:00:00Z",
                "type": "skill.invoked",
                "data": {"path": str(plan_skill), "name": "plan"},
            }
        ],
    )

    default_result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "text",
            "--codex-root",
            str(codex_root),
            "--claude-root",
            str(claude_root),
            "--copilot-root",
            str(copilot_root),
            "--agents-root",
            str(agents_root),
        ],
        env={"HOME": str(tmp_path / "home" / "user")},
    )
    assert default_result.exit_code == 0, default_result.stdout
    assert default_result.stdout.splitlines() == [
        "agent\tdate\tskill\tsession_id",
        "claude\t14 Mar 2026\tdesign\tclaude-session",
        "copilot\t15 Mar 2026\tplan\tcopilot-session",
        "codex\t13 Mar 2026\tplan\tcodex-session",
    ]

    filtered_result = RUNNER.invoke(
        build_app(),
        [
            "--format",
            "text",
            "--agent",
            "claude",
            "--agent",
            "copilot",
            "--codex-root",
            str(codex_root),
            "--claude-root",
            str(claude_root),
            "--copilot-root",
            str(copilot_root),
            "--agents-root",
            str(agents_root),
        ],
        env={"HOME": str(tmp_path / "home" / "user")},
    )
    assert filtered_result.exit_code == 0, filtered_result.stdout
    assert filtered_result.stdout.splitlines() == [
        "agent\tdate\tskill\tsession_id",
        "claude\t14 Mar 2026\tdesign\tclaude-session",
        "copilot\t15 Mar 2026\tplan\tcopilot-session",
    ]
