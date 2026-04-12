#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///

from __future__ import annotations

import dataclasses
import datetime as dt
import fnmatch
import json
import re
import shlex
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import unquote, urlparse

import typer


READ_COMMANDS = {
    "awk",
    "bat",
    "cat",
    "grep",
    "head",
    "less",
    "more",
    "perl",
    "rg",
    "sed",
    "tail",
}
SHELL_WRAPPERS = {
    "builtin",
    "command",
    "env",
    "nice",
    "nohup",
    "setsid",
    "stdbuf",
    "sudo",
    "time",
    "timeout",
}
AGENTS = ("claude", "codex", "copilot")


@dataclasses.dataclass(frozen=True)
class SkillUse:
    agent: str
    session_id: str
    timestamp: str
    skill: str

    @property
    def session_date(self) -> str:
        parsed = _parse_timestamp(self.timestamp)
        if parsed is None:
            return self.timestamp or ""
        return f"{parsed.day} {parsed:%b %Y}"

    def to_dict(self) -> dict[str, str]:
        return {
            "agent": self.agent,
            "session_date": self.session_date,
            "skill": self.skill,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
        }


def _parse_timestamp(value: str) -> dt.datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    yield value
    except OSError:
        return


def _normalize_skill_target(target: str, agents_root: Path) -> str | None:
    del agents_root
    target = target.strip()
    if not target or "SKILL.md" not in target:
        return None

    if target.startswith(("http://", "https://")):
        parsed = urlparse(target)
        target = unquote(parsed.path)

    path = Path(target)
    if path.name.casefold() != "skill.md" or len(path.parts) < 2:
        return None
    return path.parent.name or None


def _unwrap_shell_script(command: str) -> str:
    command = command.strip()
    if not command:
        return ""
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return command
    if len(tokens) >= 3 and tokens[0] in {"bash", "sh", "zsh"} and tokens[1] in {"-c", "-lc"}:
        return tokens[2]
    return command


def _split_shell_segments(command: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"\|\||&&|[;\n|]", command) if segment.strip()]


def _first_command(tokens: list[str]) -> str | None:
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if "=" in token and token.split("=", 1)[0].replace("_", "").isalnum():
            index += 1
            continue
        if token in SHELL_WRAPPERS:
            index += 1
            continue
        return Path(token).name
    return None


def _shell_skill_targets(command: str, agents_root: Path) -> list[str]:
    targets: list[str] = []
    for segment in _split_shell_segments(_unwrap_shell_script(command)):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            tokens = segment.split()
        if not tokens:
            continue
        executable = _first_command(tokens)
        if executable not in READ_COMMANDS:
            continue
        for token in tokens[1:]:
            skill = _normalize_skill_target(token, agents_root)
            if skill is not None:
                targets.append(skill)
    return targets


def _tool_argument_skill_targets(tool_name: str, arguments: Any, agents_root: Path) -> list[str]:
    tool = tool_name.lower()
    if tool in {"read", "view"} and isinstance(arguments, dict):
        path = arguments.get("file_path") or arguments.get("path")
        if isinstance(path, str):
            skill = _normalize_skill_target(path, agents_root)
            return [skill] if skill else []
        return []
    if tool == "webfetch" and isinstance(arguments, dict):
        url = arguments.get("url")
        if isinstance(url, str):
            skill = _normalize_skill_target(url, agents_root)
            return [skill] if skill else []
        return []
    if tool in {"bash", "exec_command", "shell"}:
        if isinstance(arguments, dict):
            if tool == "exec_command" and isinstance(arguments.get("cmd"), str):
                return _shell_skill_targets(arguments["cmd"], agents_root)
            command = arguments.get("command")
            if isinstance(command, str):
                return _shell_skill_targets(command, agents_root)
            if isinstance(command, list):
                return _shell_skill_targets(" ".join(str(part) for part in command), agents_root)
        if isinstance(arguments, str):
            return _shell_skill_targets(arguments, agents_root)
    return []


def _resolve_claude_skill_target(skill_name: str, cwd: str, agents_root: Path) -> str | None:
    del cwd, agents_root
    return skill_name.strip() or None


def _parse_tool_arguments(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _is_copilot_tool_success(event: dict[str, Any]) -> bool:
    data = event.get("data")
    return isinstance(data, dict) and bool(data.get("success"))


def _is_codex_tool_success(output: Any) -> bool:
    if isinstance(output, str):
        lowered = output.lower()
        if "exited with code 0" in lowered or "exit_code\":0" in lowered:
            return True
        return "exited with code" not in lowered and "error" not in lowered
    if isinstance(output, dict):
        metadata = output.get("metadata")
        if isinstance(metadata, dict) and metadata.get("exit_code") is not None:
            return int(metadata["exit_code"]) == 0
    return False


def _matches_skill_globs(skill: str, patterns: tuple[str, ...]) -> bool:
    if not patterns:
        return True
    folded = skill.casefold()
    return any(fnmatch.fnmatchcase(folded, pattern.casefold()) for pattern in patterns)


def _iter_codex_files(root: Path) -> Iterator[Path]:
    sessions = root / "sessions"
    if sessions.exists():
        for year_dir in sorted((path for path in sessions.iterdir() if path.is_dir()), reverse=True):
            for month_dir in sorted((path for path in year_dir.iterdir() if path.is_dir()), reverse=True):
                for day_dir in sorted((path for path in month_dir.iterdir() if path.is_dir()), reverse=True):
                    for path in sorted(day_dir.glob("*.jsonl"), reverse=True):
                        yield path
    archived = root / "archived_sessions"
    if archived.exists():
        for path in sorted(archived.glob("*.jsonl"), reverse=True):
            yield path


def _path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return float("-inf")


def _iter_claude_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for project_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=_path_mtime, reverse=True):
        for path in sorted(project_dir.rglob("*.jsonl"), key=_path_mtime, reverse=True):
            yield path


def _iter_copilot_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return
    for session_dir in sorted((path for path in root.iterdir() if path.is_dir()), key=_path_mtime, reverse=True):
        path = session_dir / "events.jsonl"
        if path.is_file():
            yield path


def _yield_skill(
    *,
    seen: set[tuple[str, str, str]],
    agent: str,
    session_id: str,
    timestamp: str,
    skill: str,
    skill_globs: tuple[str, ...],
) -> SkillUse | None:
    if not _matches_skill_globs(skill, skill_globs):
        return None
    key = (agent, session_id, skill)
    if key in seen:
        return None
    seen.add(key)
    return SkillUse(agent=agent, session_id=session_id, timestamp=timestamp, skill=skill)


def _scan_codex(root: Path, agents_root: Path, *, seen: set[tuple[str, str, str]], skill_globs: tuple[str, ...]) -> Iterator[SkillUse]:
    for path in _iter_codex_files(root):
        session_id = path.stem
        pending: dict[str, tuple[str, list[str]]] = {}
        for event in _load_jsonl(path):
            payload = event.get("payload")
            if event.get("type") == "session_meta" and isinstance(payload, dict):
                raw_id = payload.get("id")
                if isinstance(raw_id, str) and raw_id:
                    session_id = raw_id
                continue
            if event.get("type") != "response_item" or not isinstance(payload, dict):
                continue
            payload_type = payload.get("type")
            if payload_type == "function_call":
                args = _parse_tool_arguments(payload.get("arguments"))
                targets = _tool_argument_skill_targets(str(payload.get("name", "")), args, agents_root)
                call_id = payload.get("call_id")
                if isinstance(call_id, str) and targets:
                    pending[call_id] = (str(event.get("timestamp", "")), targets)
            elif payload_type == "function_call_output":
                call_id = payload.get("call_id")
                if not isinstance(call_id, str) or call_id not in pending:
                    continue
                if not _is_codex_tool_success(payload.get("output")):
                    pending.pop(call_id, None)
                    continue
                timestamp, targets = pending.pop(call_id)
                for skill in targets:
                    row = _yield_skill(
                        seen=seen,
                        agent="codex",
                        session_id=session_id,
                        timestamp=timestamp,
                        skill=skill,
                        skill_globs=skill_globs,
                    )
                    if row is not None:
                        yield row


def _scan_claude(root: Path, agents_root: Path, *, seen: set[tuple[str, str, str]], skill_globs: tuple[str, ...]) -> Iterator[SkillUse]:
    for path in _iter_claude_files(root):
        pending: dict[str, tuple[str, str, list[str]]] = {}
        for event in _load_jsonl(path):
            session_id = str(event.get("sessionId") or path.stem)
            timestamp = str(event.get("timestamp", ""))
            cwd = str(event.get("cwd", ""))
            message = event.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "tool_use":
                    tool_id = item.get("id")
                    if not isinstance(tool_id, str):
                        continue
                    tool_name = str(item.get("name", ""))
                    targets = _tool_argument_skill_targets(tool_name, item.get("input"), agents_root)
                    if not targets and tool_name.lower() == "skill" and isinstance(item.get("input"), dict):
                        skill_name = item["input"].get("skill")
                        if isinstance(skill_name, str):
                            target = _resolve_claude_skill_target(skill_name, cwd, agents_root)
                            targets = [target] if target is not None else []
                    if targets:
                        pending[tool_id] = (session_id, timestamp, targets)
                elif item.get("type") == "tool_result":
                    tool_id = item.get("tool_use_id")
                    if not isinstance(tool_id, str) or tool_id not in pending:
                        continue
                    if item.get("is_error") is True:
                        pending.pop(tool_id, None)
                        continue
                    matched_session, matched_ts, targets = pending.pop(tool_id)
                    for skill in targets:
                        row = _yield_skill(
                            seen=seen,
                            agent="claude",
                            session_id=matched_session,
                            timestamp=matched_ts,
                            skill=skill,
                            skill_globs=skill_globs,
                        )
                        if row is not None:
                            yield row


def _scan_copilot(root: Path, agents_root: Path, *, seen: set[tuple[str, str, str]], skill_globs: tuple[str, ...]) -> Iterator[SkillUse]:
    for path in _iter_copilot_files(root):
        session_id = path.parent.name
        pending: dict[str, tuple[str, list[str]]] = {}
        for event in _load_jsonl(path):
            timestamp = str(event.get("timestamp", ""))
            event_type = str(event.get("type", ""))
            data = event.get("data")
            if event_type == "skill.invoked" and isinstance(data, dict):
                skill = data.get("path")
                if isinstance(skill, str):
                    normalized = _normalize_skill_target(skill, agents_root)
                    if normalized is not None:
                        row = _yield_skill(
                            seen=seen,
                            agent="copilot",
                            session_id=session_id,
                            timestamp=timestamp,
                            skill=normalized,
                            skill_globs=skill_globs,
                        )
                        if row is not None:
                            yield row
                continue
            if event_type == "tool.execution_start" and isinstance(data, dict):
                tool_call_id = data.get("toolCallId")
                if not isinstance(tool_call_id, str):
                    continue
                targets = _tool_argument_skill_targets(
                    str(data.get("toolName", "")),
                    data.get("arguments"),
                    agents_root,
                )
                if targets:
                    pending[tool_call_id] = (timestamp, targets)
            elif event_type == "tool.execution_complete" and isinstance(data, dict):
                tool_call_id = data.get("toolCallId")
                if not isinstance(tool_call_id, str) or tool_call_id not in pending:
                    continue
                if not _is_copilot_tool_success(event):
                    pending.pop(tool_call_id, None)
                    continue
                matched_ts, targets = pending.pop(tool_call_id)
                for skill in targets:
                    row = _yield_skill(
                        seen=seen,
                        agent="copilot",
                        session_id=session_id,
                        timestamp=matched_ts,
                        skill=skill,
                        skill_globs=skill_globs,
                    )
                    if row is not None:
                        yield row


def iter_skill_use(
    *,
    codex_root: Path,
    claude_root: Path,
    copilot_root: Path,
    agents_root: Path,
    agents: set[str],
    skill_globs: tuple[str, ...],
) -> Iterator[SkillUse]:
    seen: set[tuple[str, str, str]] = set()
    if "claude" in agents:
        yield from _scan_claude(
            claude_root.expanduser(),
            agents_root,
            seen=seen,
            skill_globs=skill_globs,
        )
    if "copilot" in agents:
        yield from _scan_copilot(
            copilot_root.expanduser(),
            agents_root,
            seen=seen,
            skill_globs=skill_globs,
        )
    if "codex" in agents:
        yield from _scan_codex(
            codex_root.expanduser(),
            agents_root,
            seen=seen,
            skill_globs=skill_globs,
        )


def collect_skill_use(
    *,
    codex_root: Path,
    claude_root: Path,
    copilot_root: Path,
    agents_root: Path,
    agents: set[str],
    skill_globs: tuple[str, ...],
) -> list[SkillUse]:
    rows = list(
        iter_skill_use(
            codex_root=codex_root,
            claude_root=claude_root,
            copilot_root=copilot_root,
            agents_root=agents_root,
            agents=agents,
            skill_globs=skill_globs,
        )
    )
    return sorted(
        rows,
        key=lambda row: (_parse_timestamp(row.timestamp) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), row.agent, row.skill, row.session_id),
        reverse=True,
    )


def _default_format(selected: str | None) -> str:
    if selected:
        return selected
    return "text" if typer.get_text_stream("stdout").isatty() else "json"


def build_app() -> typer.Typer:
    app = typer.Typer(add_completion=False)

    @app.command()
    def main(
        agent: list[str] = typer.Option([], "--agent", help="Only scan these agents."),
        skill: list[str] = typer.Option([], "--skill", help="Only include skills matching these glob patterns."),
        format: str | None = typer.Option(None, "--format", help="Output format: text or json."),
        describe: bool = typer.Option(False, "--describe", help="Print machine-readable command metadata."),
        codex_root: Path = typer.Option(Path("~/.codex"), help="Codex log root."),
        claude_root: Path = typer.Option(Path("~/.claude/projects"), help="Claude log root."),
        copilot_root: Path = typer.Option(Path("~/.copilot/session-state"), help="Copilot session-state root."),
        agents_root: Path = typer.Option(Path("~/code/scripts/agents"), help="Base directory used to relativize SKILL.md paths."),
    ) -> None:
        if describe:
            payload = {
                "name": "skilluse",
                "description": "Detect which SKILL.md files were actually read in which sessions.",
                "options": {
                    "agent": {"type": "array", "items": list(AGENTS), "repeatable": True},
                    "skill": {"type": "array", "items": ["glob"], "repeatable": True},
                    "format": {"type": "string", "enum": ["text", "json"]},
                    "codex_root": {"type": "path"},
                    "claude_root": {"type": "path"},
                    "copilot_root": {"type": "path"},
                    "agents_root": {"type": "path"},
                },
                "output": {
                    "fields": ["agent", "session_date", "skill", "session_id", "timestamp"]
                },
            }
            typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
            raise typer.Exit()

        selected_agents = set(agent or AGENTS)
        invalid_agents = sorted(selected_agents - set(AGENTS))
        if invalid_agents:
            raise typer.BadParameter(f"Unknown agents: {', '.join(invalid_agents)}")

        output_format = _default_format(format)
        if output_format not in {"text", "json"}:
            raise typer.BadParameter("format must be 'text' or 'json'")

        skill_globs = tuple(pattern for pattern in skill if pattern)
        if output_format == "text":
            typer.echo("agent\tdate\tskill\tsession_id")
            for row in iter_skill_use(
                codex_root=codex_root,
                claude_root=claude_root,
                copilot_root=copilot_root,
                agents_root=agents_root,
                agents=selected_agents,
                skill_globs=skill_globs,
            ):
                typer.echo(f"{row.agent}\t{row.session_date}\t{row.skill}\t{row.session_id}")
            return

        rows = collect_skill_use(
            codex_root=codex_root,
            claude_root=claude_root,
            copilot_root=copilot_root,
            agents_root=agents_root,
            agents=selected_agents,
            skill_globs=skill_globs,
        )

        if output_format == "json":
            typer.echo(json.dumps([row.to_dict() for row in rows], ensure_ascii=False, indent=2))
            return

    return app


def run() -> None:
    build_app()()


if __name__ == "__main__":
    run()
