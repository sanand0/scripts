#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///

"""Summarize Codex CLI tool usage across JSONL rollout logs."""

from __future__ import annotations

import json
import shlex
from collections import Counter, defaultdict
from pathlib import Path
from typing import DefaultDict

import typer


def _clean_tool_name(raw_name: str | None) -> str:
    return raw_name or "unknown"


ERROR_KEYWORDS = (
    "failed",
    "error",
    "traceback",
    "exception",
    "permission denied",
    "no such file",
    "not found",
    "timed out",
)


def _call_succeeded(output_blob: str | None) -> bool:
    if output_blob is None:
        return False

    output_blob = output_blob.strip()
    if not output_blob:
        return True

    try:
        parsed = json.loads(output_blob)
    except json.JSONDecodeError:
        lowered = output_blob.lower()
        return not any(keyword in lowered for keyword in ERROR_KEYWORDS)

    metadata = parsed.get("metadata") if isinstance(parsed, dict) else None
    if isinstance(metadata, dict):
        exit_code = metadata.get("exit_code")
        if exit_code is not None:
            return exit_code == 0

    return True


def _first_command_token(tokens: list[str]) -> str | None:
    literal_skips = {
        "sudo",
        "env",
        "{",
        "}",
        "(",
        ")",
        "||",
        "&&",
        "|",
        ";",
        "then",
        "do",
        "done",
        "fi",
        "elif",
        "else",
    }

    def is_env_assignment(token: str) -> bool:
        if "=" not in token:
            return False
        name, _, value = token.partition("=")
        if not name or not name.replace("_", "").isalnum():
            return False
        return True

    substitution_depth = 0

    for token in tokens:
        token = token.strip()
        if not token:
            continue

        if substitution_depth > 0:
            substitution_depth += token.count("$(")
            substitution_depth -= token.count(")")
            if substitution_depth < 0:
                substitution_depth = 0
            continue

        if token == "[":
            return "test"

        if token in literal_skips:
            continue

        if token.startswith(("-", "+")) and len(token) > 1:
            continue

        if token.startswith("$("):
            balance = token.count("$(") - token.count(")")
            substitution_depth = max(balance, 1)
            continue

        if is_env_assignment(token):
            _, _, value = token.partition("=")
            if value.startswith("$("):
                balance = value.count("$(") - value.count(")")
                substitution_depth = max(balance, 1)
            continue

        if set(token) <= set("|&;{}()"):
            continue

        return token

    return tokens[0] if tokens else None


def _parse_shell_command(arguments_blob: str | None) -> str | None:
    if not arguments_blob:
        return None

    try:
        arguments = json.loads(arguments_blob)
    except json.JSONDecodeError:
        return None

    command = arguments.get("command") if isinstance(arguments, dict) else None
    if not isinstance(command, list) or not command:
        return None

    normalized = [item for item in command if isinstance(item, str)]
    if not normalized:
        return None

    if len(normalized) >= 3 and normalized[0] == "bash" and normalized[1] == "-lc":
        script = normalized[2].lstrip()
        if not script:
            return "bash"
        try:
            tokens = shlex.split(script, posix=True)
        except ValueError:
            tokens = script.split()
        return _first_command_token(tokens) or "bash"

    return _first_command_token(normalized) or normalized[0]


def _parse_log(path: Path) -> tuple[Counter[str], dict[str, Counter[str]], dict[str, Counter[str]]]:
    """Return totals, per-tool stats, and shell command stats for a log."""

    totals: Counter[str] = Counter()
    tool_stats: DefaultDict[str, Counter[str]] = defaultdict(Counter)
    shell_stats: DefaultDict[str, Counter[str]] = defaultdict(Counter)
    calls: dict[str, tuple[str, str | None]] = {}
    completed: set[str] = set()

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "response_item":
                continue

            payload = entry.get("payload") or {}
            payload_type = payload.get("type", "")
            call_id = payload.get("call_id")

            if payload_type.endswith("_call"):
                if call_id:
                    name = _clean_tool_name(payload.get("name"))
                    shell_command = (
                        _parse_shell_command(payload.get("arguments")) if name == "shell" else None
                    )
                    calls[call_id] = (name, shell_command)
                continue

            if not payload_type.endswith("_call_output") or not call_id or call_id in completed:
                continue

            call_info = calls.get(call_id)
            tool_name = _clean_tool_name(call_info[0] if call_info else None)
            success = _call_succeeded(payload.get("output"))
            key = "success" if success else "failure"
            tool_stats[tool_name][key] += 1
            totals[key] += 1
            completed.add(call_id)

            if tool_name == "shell":
                command_label = (call_info[1] if call_info else None) or "unknown"
                shell_stats[command_label][key] += 1

    return totals, dict(tool_stats), dict(shell_stats)


app = typer.Typer(add_completion=False)
root = typer.Argument(
    Path.home() / ".codex", exists=True, file_okay=False, dir_okay=True, resolve_path=True
)


@app.command()
def main(root: Path = root) -> None:
    """Print per-log and overall tool usage summaries."""

    logs = sorted(root.rglob("*.jsonl"))
    if not logs:
        typer.echo(f"No JSONL logs found under {root}")
        raise typer.Exit(code=1)

    reports = [_parse_log(path) for path in logs]

    overall: Counter[str] = Counter()
    overall_tool_stats: DefaultDict[str, Counter[str]] = defaultdict(Counter)
    overall_shell_breakdown: DefaultDict[str, Counter[str]] = defaultdict(Counter)

    for totals, tools, shells in reports:
        overall.update(totals)
        for tool, counts in tools.items():
            overall_tool_stats[tool].update(counts)
        for cmd, counts in shells.items():
            overall_shell_breakdown[cmd].update(counts)

    typer.echo(f"{len(reports)} logs. {overall['success'] + overall['failure']} calls")
    typer.echo(f"Success={overall['success']}. Failure={overall['failure']}\n")

    sorted_tools = sorted(
        overall_tool_stats.items(),
        key=lambda item: item[1]["success"] + item[1]["failure"],
        reverse=True,
    )
    for tool, counts in sorted_tools:
        total = counts["success"] + counts["failure"]
        fail = counts["failure"] / total if total > 0 else 0.0
        typer.echo(f"- {tool}: {total}. fail={counts['failure']} ({fail:.1%})")
        if tool == "shell" and overall_shell_breakdown:
            sorted_cmds = sorted(
                overall_shell_breakdown.items(),
                key=lambda item: item[1]["success"] + item[1]["failure"],
                reverse=True,
            )
            for cmd, cmd_counts in sorted_cmds:
                cmd_total = cmd_counts["success"] + cmd_counts["failure"]
                fail = cmd_counts["failure"] / cmd_total if cmd_total > 0 else 0.0
                typer.echo(f"  - {cmd}: {cmd_total}. fail={cmd_counts['failure']} ({fail:.1%})")


if __name__ == "__main__":
    app()
