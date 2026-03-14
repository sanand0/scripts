#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["bashlex>=0.18", "orjson>=3.10", "typer>=0.12"]
# ///

"""Build and incrementally update `~/.codex/sessions/tags.csv`."""

from __future__ import annotations

import csv
import os
import re
import shlex
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import orjson
import typer

try:
    import bashlex
except Exception:  # noqa: BLE001
    bashlex = None

TAGGER_VERSION = "2026-03-03.2"
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

REQUIRED_COLUMNS = [
    "session_key",
    "session_file",
    "session_id",
    "session_format",
    "date",
    "started_at",
    "ended_at",
    "duration_seconds",
    "file_size_bytes",
    "event_count",
    "cwd",
    "model",
    "model_provider",
    "approval_policy",
    "cli_version",
    "is_subagent",
    "user_message_count",
    "assistant_message_count",
    "developer_message_count",
    "other_message_count",
    "first_user_chars",
    "first_user_preview",
    "objective_preview",
    "total_user_chars",
    "max_user_chars",
    "tool_call_count",
    "tool_output_count",
    "tool_success_count",
    "tool_failure_count",
    "has_tool_failures",
    "tool_error_rate",
    "tools_used",
    "top_tools",
    "top_failing_tools",
    "shell_command_count",
    "shell_error_rate",
    "command_diversity",
    "skill_count",
    "executable_count",
    "top_shell_commands",
    "skill_count",
    "skills_used",
    "top_skills",
    "executable_count",
    "executables_used",
    "top_executables",
    "tool_duration_total_seconds",
    "tool_duration_avg_seconds",
    "time_to_first_tool_seconds",
    "time_to_first_edit_seconds",
    "time_to_first_verification_seconds",
    "apply_patch_count",
    "apply_patch_success_rate",
    "files_edited_count",
    "files_per_patch",
    "files_edited",
    "tool_calls_per_minute",
    "edits_per_minute",
    "feature_exec_command",
    "feature_apply_patch",
    "feature_update_plan",
    "feature_subagents",
    "feature_parallel",
    "feature_web",
    "feature_image",
    "reasoning_count",
    "token_input_total",
    "token_output_total",
    "token_total",
    "token_cached_input",
    "plan_update_count",
    "plan_before_edit",
    "subagent_spawn_count",
    "parallel_tool_call_count",
    "verification_command_count",
    "verification_after_edit",
    "verification_commands_per_edit",
    "lint_command_count",
    "test_command_count",
    "build_command_count",
    "git_command_count",
    "commit_command_count",
    "pr_command_count",
    "prompt_has_file_paths",
    "prompt_has_constraints",
    "prompt_has_acceptance_criteria",
    "prompt_has_numbered_steps",
    "prompt_has_agents_md",
    "prompt_has_plans_md",
    "prompt_minimal_style",
    "workflow_mode",
    "workflow_phase_tags",
    "intent_tags",
    "parse_status",
    "parse_error",
    "tagger_version",
    "tagged_at",
]

SUBAGENT_TOOLS = {
    "spawn_agent",
    "send_input",
    "wait",
    "close_agent",
    "resume_agent",
    "spawn_agents_on_csv",
}
WEB_TOOLS = {
    "search_query",
    "open",
    "click",
    "find",
    "screenshot",
    "image_query",
    "sports",
    "finance",
    "weather",
    "time",
}
WEB_TOOL_PREFIXES = ("playwright__", "chrome-devtools__", "web_", "browser_")
IMAGE_TOOLS = {"view_image", "image_query", "screenshot"}
WEB_EXECUTABLES = {
    "curl",
    "wget",
    "w3m",
    "lynx",
    "websocat",
    "wscat",
    "playwright",
    "chrome",
    "chromium",
    "google-chrome",
    "firefox",
    "open",
    "xdg-open",
}

PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.MULTILINE)
PATH_HINT_RE = re.compile(r"(?:^|[\s`'\"(])(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+(?:\.\w+)?")
NUMBERED_STEP_RE = re.compile(r"(?m)^\s*\d+\.\s+\S")
SKILL_PATH_RE = re.compile(r"agents/(?P<skill>[^\s`'\"()]+?)/SKILL\.md", re.IGNORECASE)
HEREDOC_START_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")

EXEC_WRAPPERS = {
    "sudo",
    "env",
    "command",
    "builtin",
    "time",
    "nohup",
    "nice",
    "ionice",
    "chrt",
    "stdbuf",
    "timeout",
    "setsid",
    "xargs",
    "export",
    "source",
    ".",
    "set",
    "unset",
    "alias",
    "unalias",
    "cd",
    "pushd",
    "popd",
}
NON_EXECUTABLE_WORDS = {
    "if",
    "then",
    "fi",
    "for",
    "while",
    "until",
    "do",
    "done",
    "case",
    "esac",
    "in",
    "elif",
    "else",
    "function",
    "select",
    "const",
    "let",
    "var",
    "def",
    "class",
    "return",
    "from",
    "import",
}

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "bugfix": ("fix", "bug", "failing", "broken", "error", "regression", "issue"),
    "feature": ("implement", "add", "build", "create", "new feature", "support"),
    "refactor": ("refactor", "cleanup", "restructure", "simplify"),
    "testing": ("test", "pytest", "unit test", "integration test", "coverage"),
    "docs": ("readme", "documentation", "docs", "comment"),
    "performance": ("performance", "optimize", "faster", "speed", "latency"),
    "frontend": ("frontend", "ui", "ux", "css", "html", "react", "vue", "svelte"),
    "backend": ("backend", "api", "server", "endpoint", "database", "sql"),
    "data_analysis": ("analysis", "dataset", "dataframe", "model", "prediction", "csv"),
    "devops": ("docker", "deploy", "ci", "infra", "kubernetes", "pipeline"),
    "code_review": ("review", "pull request", "pr feedback", "audit"),
    "automation": ("script", "automate", "batch", "cron", "workflow"),
    "research": ("investigate", "explore", "compare", "evaluate", "research"),
}

SCAFFOLDING_PREFIXES = (
    "# agents.md instructions",
    "<environment_context>",
    "<permissions instructions>",
)

CONSTRAINT_KEYWORDS = (
    "must",
    "should",
    "do not",
    "don't",
    "avoid",
    "never",
    "only",
    "require",
    "constraint",
    "idempotent",
    "efficient",
    "fast",
)
ACCEPTANCE_KEYWORDS = (
    "test",
    "verify",
    "acceptance",
    "success criteria",
    "expected output",
    "run and test",
    "done when",
)
TEST_COMMAND_PATTERNS = (
    " test",
    "pytest",
    "unittest",
    "vitest",
    "jest",
    "go test",
    "cargo test",
    "ctest",
    "nosetests",
    "tox",
)
LINT_COMMAND_PATTERNS = (
    "lint",
    "ruff",
    "flake8",
    "pylint",
    "eslint",
    "stylelint",
    "shellcheck",
    "golangci-lint",
    "mypy",
    "pyright",
    "rubocop",
    "swiftlint",
    "biome",
    "typecheck",
    "tsc --noemit",
)
BUILD_COMMAND_PATTERNS = (
    " build",
    "compile",
    "make",
    "cmake",
    "bazel build",
    "cargo build",
    "go build",
    "mvn package",
    "gradle build",
    "npm run build",
    "pnpm build",
    "yarn build",
)
GIT_COMMAND_PATTERNS = ("git ", "gh ", "git\n", "gh\n")
COMMIT_COMMAND_PATTERNS = ("git commit", "git merge", "git rebase")
PR_COMMAND_PATTERNS = ("gh pr", "create a pr", "pull request")

app = typer.Typer(add_completion=False)


@dataclass(slots=True)
class UpdateSummary:
    total_sessions: int
    queued_sessions: int
    processed_sessions: int
    skipped_sessions: int
    parse_errors: int


NUMERIC_COLUMNS = {
    "duration_seconds",
    "event_count",
    "file_size_bytes",
    "user_message_count",
    "assistant_message_count",
    "developer_message_count",
    "other_message_count",
    "first_user_chars",
    "total_user_chars",
    "max_user_chars",
    "tool_call_count",
    "tool_output_count",
    "tool_success_count",
    "tool_failure_count",
    "shell_command_count",
    "apply_patch_count",
    "files_edited_count",
    "reasoning_count",
    "token_input_total",
    "token_output_total",
    "token_total",
    "token_cached_input",
    "tool_error_rate",
    "shell_error_rate",
    "tool_duration_total_seconds",
    "tool_duration_avg_seconds",
    "time_to_first_tool_seconds",
    "time_to_first_edit_seconds",
    "time_to_first_verification_seconds",
    "apply_patch_success_rate",
    "files_per_patch",
    "tool_calls_per_minute",
    "edits_per_minute",
    "plan_update_count",
    "subagent_spawn_count",
    "parallel_tool_call_count",
    "verification_command_count",
    "verification_commands_per_edit",
    "lint_command_count",
    "test_command_count",
    "build_command_count",
    "git_command_count",
    "commit_command_count",
    "pr_command_count",
    "command_diversity",
}
TEXT_NONE_COLUMNS = {
    "tools_used",
    "top_tools",
    "top_failing_tools",
    "top_shell_commands",
    "skills_used",
    "top_skills",
    "executables_used",
    "top_executables",
    "files_edited",
    "workflow_phase_tags",
}
TEXT_UNKNOWN_COLUMNS = {
    "cwd",
    "model",
    "model_provider",
    "approval_policy",
    "cli_version",
    "workflow_mode",
}
BOOL_COLUMNS = {
    "has_tool_failures",
    "feature_exec_command",
    "feature_apply_patch",
    "feature_update_plan",
    "feature_subagents",
    "feature_parallel",
    "feature_web",
    "feature_image",
    "plan_before_edit",
    "verification_after_edit",
    "prompt_has_file_paths",
    "prompt_has_constraints",
    "prompt_has_acceptance_criteria",
    "prompt_has_numbered_steps",
    "prompt_has_agents_md",
    "prompt_has_plans_md",
    "prompt_minimal_style",
}


@dataclass(frozen=True, slots=True)
class TagDoc:
    """Documentation for a CSV tag/column."""

    construction: str
    usefulness: str


TAG_DOCS: dict[str, TagDoc] = {
    "session_key": TagDoc(
        "Relative path from `sessions_root` to the session file.",
        "Stable primary key to join `tags.csv` with raw session logs across machines.",
    ),
    "session_file": TagDoc(
        "Absolute path to the underlying `.json` or `.jsonl` file.",
        "Lets you jump directly into the source session for deeper forensics.",
    ),
    "session_id": TagDoc(
        "From `session_meta.payload.id` (or legacy `session.id`), fallback to filename stem.",
        "Tracks one logical run across derived reports, traces, and dashboards.",
    ),
    "session_format": TagDoc(
        "File extension without dot (`json` or `jsonl`).",
        "Helps detect parser drift and migration progress between log formats.",
    ),
    "date": TagDoc(
        "UTC date slice (`YYYY-MM-DD`) from `started_at`.",
        "Supports daily rollups and trend charts for throughput and reliability.",
    ),
    "started_at": TagDoc(
        "Preferred: session timestamp from metadata; fallback: first event timestamp; fallback: file mtime.",
        "Anchor timestamp for lead-time and time-to-action workflow analysis.",
    ),
    "ended_at": TagDoc(
        "Last observed event timestamp; fallback to `started_at`.",
        "Combined with `started_at` to estimate active session elapsed time.",
    ),
    "duration_seconds": TagDoc(
        "Integer difference between `ended_at` and `started_at`, clamped at >= 0.",
        "Core denominator for speed metrics (`tool_calls_per_minute`, `edits_per_minute`).",
    ),
    "file_size_bytes": TagDoc(
        "Raw file size from filesystem stat.",
        "Quick proxy for session complexity and log verbosity.",
    ),
    "event_count": TagDoc(
        "Count of parsed records/events in the session stream.",
        "High-level activity volume for triage and outlier detection.",
    ),
    "cwd": TagDoc(
        "From `session_meta.payload.cwd` when available.",
        "Identifies which repository/project consumed agent time.",
    ),
    "model": TagDoc(
        "From session metadata or turn context model field.",
        "Enables model-level productivity and reliability comparisons.",
    ),
    "model_provider": TagDoc(
        "From `session_meta.payload.model_provider`.",
        "Supports provider-level cost/performance segmentation.",
    ),
    "approval_policy": TagDoc(
        "From turn context (`never`, `on-request`, etc.) when logged.",
        "Explains tool execution friction and command-failure patterns.",
    ),
    "cli_version": TagDoc(
        "From `session_meta.payload.cli_version`.",
        "Correlates behavior changes with specific CLI releases.",
    ),
    "is_subagent": TagDoc(
        "`1` when session source indicates subagent/thread-spawn metadata; else `0`.",
        "Separates top-level work from delegated work for true orchestration metrics.",
    ),
    "user_message_count": TagDoc(
        "Count of user-role messages in response items.",
        "Measures dialog turn count and requirement churn per task.",
    ),
    "assistant_message_count": TagDoc(
        "Count of assistant-role messages.",
        "Useful to track reporting verbosity and interaction style.",
    ),
    "developer_message_count": TagDoc(
        "Count of developer-role messages.",
        "Helps quantify instruction scaffolding overhead in sessions.",
    ),
    "other_message_count": TagDoc(
        "Count of message payloads with non user/assistant/developer roles.",
        "Detects unusual message-role patterns that may impact parsing.",
    ),
    "first_user_chars": TagDoc(
        "Character length of first meaningful user objective (non scaffolding).",
        "Proxy for prompt scope and instruction density.",
    ),
    "first_user_preview": TagDoc(
        "Normalized and truncated preview of the first raw user message.",
        "Fast human scan to understand what kicked off the session.",
    ),
    "objective_preview": TagDoc(
        "Normalized/truncated first non-scaffolding user objective.",
        "Captures real goal statement for intent clustering.",
    ),
    "total_user_chars": TagDoc(
        "Sum of character lengths across all user messages.",
        "Approximates total requirements bandwidth consumed.",
    ),
    "max_user_chars": TagDoc(
        "Maximum character length among user messages.",
        "Flags oversized prompts that often require stricter decomposition.",
    ),
    "tool_call_count": TagDoc(
        "Count of `function_call` + `custom_tool_call` records.",
        "Primary indicator of agentic execution intensity.",
    ),
    "tool_output_count": TagDoc(
        "Count of unique call outputs (`function_call_output` + `custom_tool_call_output`).",
        "Denominator for execution reliability and latency metrics.",
    ),
    "tool_success_count": TagDoc(
        "Outputs classified as success (exit code 0 or no error signature).",
        "Used to evaluate tool reliability under real workloads.",
    ),
    "tool_failure_count": TagDoc(
        "Outputs classified as failure (non-zero exit code/status failed/error signatures).",
        "Pinpoints sessions with execution friction needing harness or prompt fixes.",
    ),
    "has_tool_failures": TagDoc(
        "`1` when `tool_failure_count > 0`, else `0`.",
        "Simple filter for failure-driven debugging queues.",
    ),
    "tool_error_rate": TagDoc(
        "`tool_failure_count / tool_output_count` (0 when no outputs).",
        "Comparable reliability metric across sessions of different sizes.",
    ),
    "tools_used": TagDoc(
        "Alphabetically sorted unique tool names joined with `|`.",
        "High-level capability footprint used in the session.",
    ),
    "top_tools": TagDoc(
        "Top tool frequencies as `tool:count` joined with `|`.",
        "Shows dominant execution modality (editing-heavy vs exploration-heavy).",
    ),
    "top_failing_tools": TagDoc(
        "Top failing tools as `tool:fail_count` joined with `|`.",
        "Helps prioritize targeted reliability improvements per tool.",
    ),
    "shell_command_count": TagDoc(
        "Number of shell-like calls (`exec_command`/`shell`) observed.",
        "Measures dependence on terminal workflow vs direct structured tools.",
    ),
    "shell_error_rate": TagDoc(
        "Failure rate restricted to shell-like tools only.",
        "Separates command/runtime friction from non-shell tool failures.",
    ),
    "command_diversity": TagDoc(
        "Count of distinct first shell command tokens (e.g., `rg`, `git`, `pytest`).",
        "Signals breadth of workflow coverage and command specialization.",
    ),
    "top_shell_commands": TagDoc(
        "Top shell command tokens as `command:count` joined with `|`.",
        "Reveals dominant activity patterns (search, build, test, git, etc.).",
    ),
    "skill_count": TagDoc(
        "Count of distinct skills inferred from shell commands reading `agents/*/SKILL.md`.",
        "Shows how often sessions rely on reusable skill instructions.",
    ),
    "skills_used": TagDoc(
        "Sorted unique skill identifiers (e.g., `data-story`, `.system/skill-creator`) joined with `|`.",
        "Enables analysis of which skill playbooks drive successful sessions.",
    ),
    "top_skills": TagDoc(
        "Most frequent inferred skills as `skill:count` joined with `|`.",
        "Highlights dominant guidance patterns in multi-step tasks.",
    ),
    "executable_count": TagDoc(
        "Count of distinct executables inferred from parsed shell scripts/commands.",
        "Measures workflow breadth across CLI tools and build/test systems.",
    ),
    "executables_used": TagDoc(
        "Sorted unique executable names (command words) joined with `|`.",
        "Provides a compact dependency surface for agent-run tooling.",
    ),
    "top_executables": TagDoc(
        "Most frequent executables as `name:count` joined with `|`.",
        "Identifies primary command-line workflows to optimize or cache.",
    ),
    "tool_duration_total_seconds": TagDoc(
        "Sum of `metadata.duration_seconds` extracted from tool outputs when present.",
        "Approximates wall-clock effort spent in tool execution.",
    ),
    "tool_duration_avg_seconds": TagDoc(
        "Average tool output duration over outputs with reported duration.",
        "Detects latency regressions in command/tool execution loops.",
    ),
    "time_to_first_tool_seconds": TagDoc(
        "Seconds from session start to first tool call timestamp.",
        "Measures how quickly the agent transitions from reading to acting.",
    ),
    "time_to_first_edit_seconds": TagDoc(
        "Seconds from session start to first `apply_patch` call.",
        "Tracks edit readiness and planning/exploration overhead.",
    ),
    "time_to_first_verification_seconds": TagDoc(
        "Seconds from session start to first verification command (test/lint/build).",
        "Shows when correctness checks start in the task lifecycle.",
    ),
    "apply_patch_count": TagDoc(
        "Count of `apply_patch` tool calls.",
        "Primary proxy for code-edit intent and implementation activity.",
    ),
    "apply_patch_success_rate": TagDoc(
        "Success ratio over outputs whose originating tool call was `apply_patch`.",
        "Highlights patch syntax/hunk-quality issues in editing loops.",
    ),
    "files_edited_count": TagDoc(
        "Unique files inferred from patch headers (`*** Add/Update/Delete File:`).",
        "Size of code surface changed; useful for review risk estimation.",
    ),
    "files_per_patch": TagDoc(
        "`files_edited_count / apply_patch_count` (0 if no patches).",
        "Captures granularity of edits (surgical vs wide-sweep patching).",
    ),
    "files_edited": TagDoc(
        "Sorted unique edited file paths joined with `|`.",
        "Direct context for post-session audit and changelog generation.",
    ),
    "tool_calls_per_minute": TagDoc(
        "`tool_call_count / (duration_seconds / 60)` when duration > 0.",
        "Throughput metric for overall execution cadence.",
    ),
    "edits_per_minute": TagDoc(
        "`apply_patch_count / (duration_seconds / 60)` when duration > 0.",
        "Editing cadence useful for comparing fast-iterate vs deep-analysis sessions.",
    ),
    "feature_exec_command": TagDoc(
        "`1` if `exec_command` or `shell` was used.",
        "Feature adoption signal for terminal-centric workflows.",
    ),
    "feature_apply_patch": TagDoc(
        "`1` if `apply_patch` was used.",
        "Feature adoption signal for structured patch editing.",
    ),
    "feature_update_plan": TagDoc(
        "`1` if planning tool (`update_plan`) was used.",
        "Tracks plan-first behavior recommended in long tasks.",
    ),
    "feature_subagents": TagDoc(
        "`1` if any subagent tool (`spawn_agent`, `wait`, etc.) was used.",
        "Measures delegation/orchestration maturity.",
    ),
    "feature_parallel": TagDoc(
        "`1` if parallel wrapper tool was used.",
        "Detects explicit parallelization behavior for throughput optimization.",
    ),
    "feature_web": TagDoc(
        "`1` if web tools were used (including prefixed browser/devtools tools) or shell commands hit web protocols/executables.",
        "Shows whether external research/verification was incorporated.",
    ),
    "feature_image": TagDoc(
        "`1` if image-oriented tools were used.",
        "Identifies visual-debug/inspection workflows.",
    ),
    "reasoning_count": TagDoc(
        "Count of reasoning payload items.",
        "Proxy for deliberation density during execution.",
    ),
    "token_input_total": TagDoc(
        "Max observed cumulative `input_tokens` from token_count events.",
        "Cost and context-load indicator aligned with OTel token usage patterns.",
    ),
    "token_output_total": TagDoc(
        "Max observed cumulative `output_tokens` from token_count events.",
        "Measures response generation volume and cost contribution.",
    ),
    "token_total": TagDoc(
        "Max observed cumulative `total_tokens` from token_count events.",
        "Session-level total token budget consumed.",
    ),
    "token_cached_input": TagDoc(
        "Max observed cumulative `cached_input_tokens` when provided.",
        "Helps estimate cache effectiveness and context reuse.",
    ),
    "plan_update_count": TagDoc(
        "Count of explicit `update_plan` tool calls.",
        "Quantifies how actively the session maintained a living plan.",
    ),
    "plan_before_edit": TagDoc(
        "`1` if first plan update occurred at/before first edit; else `0`.",
        "Checks adherence to plan-first workflows for complex tasks.",
    ),
    "subagent_spawn_count": TagDoc(
        "Count of `spawn_agent` calls.",
        "Direct measure of subagent delegation frequency.",
    ),
    "parallel_tool_call_count": TagDoc(
        "Count of `parallel` tool calls.",
        "Tracks explicit batching/parallel IO optimization behavior.",
    ),
    "verification_command_count": TagDoc(
        "Count of shell commands classified as test/lint/build verification.",
        "Measures how consistently sessions include quality gates.",
    ),
    "verification_after_edit": TagDoc(
        "`1` if verification command appears after first edit; else `0`.",
        "Core signal for edit-then-validate loop quality.",
    ),
    "verification_commands_per_edit": TagDoc(
        "`verification_command_count / apply_patch_count` (0 if no edits).",
        "Balances implementation speed against verification rigor.",
    ),
    "lint_command_count": TagDoc(
        "Count of shell commands matching lint/typecheck patterns.",
        "Tracks static-quality enforcement habits.",
    ),
    "test_command_count": TagDoc(
        "Count of shell commands matching test patterns.",
        "Tracks dynamic validation and regression prevention habits.",
    ),
    "build_command_count": TagDoc(
        "Count of shell commands matching build/compile patterns.",
        "Tracks integration and compile-safety checks.",
    ),
    "git_command_count": TagDoc(
        "Count of shell commands indicating git/GitHub CLI usage.",
        "Measures SCM integration during agent sessions.",
    ),
    "commit_command_count": TagDoc(
        "Count of shell commands matching commit/merge/rebase actions.",
        "Captures change-finalization frequency.",
    ),
    "pr_command_count": TagDoc(
        "Count of shell commands or objective text matching PR creation actions.",
        "Signals handoff readiness and review workflow integration.",
    ),
    "prompt_has_file_paths": TagDoc(
        "`1` if objective prompt contains concrete file path hints via regex.",
        "Proxy for issue-style specificity that improves agent grounding.",
    ),
    "prompt_has_constraints": TagDoc(
        "`1` if objective includes constraint keywords (`must`, `avoid`, `idempotent`, ...).",
        "Signals explicit guardrails that reduce misalignment and rework.",
    ),
    "prompt_has_acceptance_criteria": TagDoc(
        "`1` if objective includes verification/success language (`test`, `verify`, `done when`, ...).",
        "Predictor of sessions that end with measurable completion criteria.",
    ),
    "prompt_has_numbered_steps": TagDoc(
        "`1` if objective includes numbered steps/list structure.",
        "Indicates decomposition quality for complex multi-part tasks.",
    ),
    "prompt_has_agents_md": TagDoc(
        "`1` if objective explicitly references `AGENTS.md`.",
        "Tracks persistent-context usage pattern recommended for coding agents.",
    ),
    "prompt_has_plans_md": TagDoc(
        "`1` if objective references `PLAN.md`, `PLANS.md`, or `ExecPlan`.",
        "Tracks adoption of long-horizon planning documents.",
    ),
    "prompt_minimal_style": TagDoc(
        "`1` when objective is concise (short char and word counts), else `0`.",
        "Measures adherence to minimal-prompt guidance (`less is more`).",
    ),
    "workflow_mode": TagDoc(
        "Rule-based classification from objective keywords + edit behavior (e.g., bugfix, refactor, review).",
        "Supports mode-specific optimization (different prompts/tools per task type).",
    ),
    "workflow_phase_tags": TagDoc(
        "Derived phase markers joined by `|` (`planned`, `explore`, `implement`, `verify`, `handoff`, `delegate`).",
        "Lets you see where sessions stall and which phase needs improvement.",
    ),
    "intent_tags": TagDoc(
        "Keyword-derived high-level intent tags from objective text.",
        "Useful for cohorting sessions by user goal.",
    ),
    "parse_status": TagDoc(
        "`ok` when parse succeeded, `error` when parsing/analyzing failed.",
        "Allows safe filtering before analytics and quick parser QA.",
    ),
    "parse_error": TagDoc(
        "Normalized/truncated exception text when parse_status is `error`; `-` otherwise.",
        "Debug surface for evolving log-format compatibility issues.",
    ),
    "tagger_version": TagDoc(
        "Static script version string used when row was produced.",
        "Enables reproducibility and migration control when tags evolve.",
    ),
    "tagged_at": TagDoc(
        "UTC timestamp when row was generated/updated.",
        "Supports freshness monitoring and incremental backfill audits.",
    ),
}

_missing_tag_docs = [column for column in REQUIRED_COLUMNS if column not in TAG_DOCS]
if _missing_tag_docs:
    raise RuntimeError(f"TAG_DOCS missing entries for: {_missing_tag_docs}")


def _safe_json_loads(blob: Any) -> Any:
    if isinstance(blob, (bytes, bytearray)):
        try:
            return orjson.loads(blob)
        except orjson.JSONDecodeError:
            return None
    if isinstance(blob, str):
        text = blob.strip()
        if not text:
            return None
        try:
            return orjson.loads(text)
        except orjson.JSONDecodeError:
            return None
    if isinstance(blob, (dict, list)):
        return blob
    return None


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunk for chunk in chunks if chunk)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, limit: int = 280) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _strip_prompt_scaffolding(text: str) -> str:
    if not text.strip():
        return ""

    cleaned = text
    for open_tag, close_tag in (
        ("<permissions instructions>", "</permissions instructions>"),
        ("<environment_context>", "</environment_context>"),
        ("<instructions>", "</instructions>"),
    ):
        cleaned = re.sub(
            rf"(?is){re.escape(open_tag)}.*?{re.escape(close_tag)}",
            "\n",
            cleaned,
        )

    cleaned = re.sub(r"(?im)^\s*#\s*agents\.md instructions.*$", "", cleaned)
    cleaned = re.sub(r"(?is)available tools:\s*.*?(?=\n\s*#|\n\s*<|$)", "\n", cleaned)
    cleaned = re.sub(r"(?is)##\s*skills\s*.*?(?=\n\s*#|\n\s*<|$)", "\n", cleaned)
    cleaned = re.sub(r"(?is)###\s*how to use skills\s*.*?(?=\n\s*#|\n\s*<|$)", "\n", cleaned)

    lines = [line for line in cleaned.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_empty(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _is_scaffolding_message(text: str) -> bool:
    stripped = _strip_prompt_scaffolding(text)
    normalized = _normalize(stripped).lower()
    if not normalized:
        return True
    if normalized.startswith(SCAFFOLDING_PREFIXES):
        return True
    if "available tools:" in normalized and "## skills" in normalized:
        return True
    return False


def _safe_float(value: Any) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    return 0.0


def _analyze_tool_output(output_blob: Any) -> tuple[bool, float]:
    parsed = _safe_json_loads(output_blob)
    duration_seconds = 0.0

    if isinstance(parsed, dict):
        metadata = parsed.get("metadata")
        if isinstance(metadata, dict):
            duration_seconds = max(0.0, _safe_float(metadata.get("duration_seconds")))
            if metadata.get("exit_code") is not None:
                return _safe_int(metadata["exit_code"]) == 0, duration_seconds
        return True, duration_seconds

    text = ""
    if isinstance(output_blob, str):
        text = output_blob.strip()
    if not text:
        return True, duration_seconds
    lowered = text.lower()
    return (not any(keyword in lowered for keyword in ERROR_KEYWORDS), duration_seconds)


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
        name, _, _ = token.partition("=")
        return bool(name) and name.replace("_", "").isalnum()

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
            continue
        if set(token) <= set("|&;{}()"):
            continue
        return token

    return tokens[0] if tokens else None


def _command_from_exec_command(cmd: str) -> str | None:
    cmd = cmd.strip()
    if not cmd:
        return None
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError:
        tokens = cmd.split()
    if not tokens:
        return None
    if len(tokens) >= 3 and tokens[0] in {"bash", "sh", "zsh"} and tokens[1] in {"-lc", "-c"}:
        script = tokens[2]
        try:
            inner = shlex.split(script, posix=True)
        except ValueError:
            inner = script.split()
        return _first_command_token(inner) or tokens[0]
    return _first_command_token(tokens) or tokens[0]


def _command_from_shell_arguments(args_obj: dict[str, Any]) -> str | None:
    command = args_obj.get("command")
    if isinstance(command, list):
        normalized = [item for item in command if isinstance(item, str)]
        if not normalized:
            return None
        if len(normalized) >= 3 and normalized[0] in {"bash", "sh", "zsh"} and normalized[1] in {
            "-lc",
            "-c",
        }:
            script = normalized[2].strip()
            if not script:
                return normalized[0]
            try:
                tokens = shlex.split(script, posix=True)
            except ValueError:
                tokens = script.split()
            return _first_command_token(tokens) or normalized[0]
        return _first_command_token(normalized) or normalized[0]
    return None


def _shell_command_label(tool_name: str, arguments: Any) -> str | None:
    args_obj = _safe_json_loads(arguments)
    if not isinstance(args_obj, dict):
        return None

    if tool_name == "exec_command":
        cmd = args_obj.get("cmd")
        if isinstance(cmd, str):
            return _command_from_exec_command(cmd)
        return None
    if tool_name == "shell":
        return _command_from_shell_arguments(args_obj)
    return None


def _shell_command_text(tool_name: str, arguments: Any) -> str:
    args_obj = _safe_json_loads(arguments)
    if not isinstance(args_obj, dict):
        return ""

    if tool_name == "exec_command":
        cmd = args_obj.get("cmd")
        if not isinstance(cmd, str):
            return ""
        cmd = cmd.strip()
        if not cmd:
            return ""
        try:
            tokens = shlex.split(cmd, posix=True)
        except ValueError:
            tokens = cmd.split()
        if len(tokens) >= 3 and tokens[0] in {"bash", "sh", "zsh"} and tokens[1] in {"-lc", "-c"}:
            return tokens[2].strip()
        return cmd

    if tool_name == "shell":
        command = args_obj.get("command")
        if isinstance(command, list):
            tokens = [item for item in command if isinstance(item, str)]
            if len(tokens) >= 3 and tokens[0] in {"bash", "sh", "zsh"} and tokens[1] in {"-lc", "-c"}:
                return tokens[2].strip()
            return " ".join(tokens).strip()
    return ""


def _looks_like_env_assignment(token: str) -> bool:
    if "=" not in token:
        return False
    name, _, _ = token.partition("=")
    if not name:
        return False
    return name.replace("_", "").isalnum()


def _normalize_executable_token(token: str) -> str | None:
    token = token.strip().strip("\"'`")
    if not token:
        return None
    if token in {"{", "}", "(", ")", "[", "]"}:
        return None
    if token.startswith("$(") or token.startswith("${") or token.startswith("`"):
        return None
    token = token.rstrip(";,")
    token = token.split("/")[-1]
    token = token.strip()
    if not token:
        return None
    if token.lower() in NON_EXECUTABLE_WORDS:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+-]*", token):
        return None
    return token


def _command_word_from_tokens(tokens: list[str]) -> str | None:
    i = 0
    while i < len(tokens):
        token = tokens[i]
        lowered = token.lower()

        if _looks_like_env_assignment(token):
            i += 1
            continue
        if lowered == "env":
            i += 1
            while i < len(tokens) and _looks_like_env_assignment(tokens[i]):
                i += 1
            continue
        if lowered in EXEC_WRAPPERS:
            i += 1
            continue
        normalized = _normalize_executable_token(token)
        if normalized:
            return normalized
        i += 1
    return None


def _walk_bash_nodes(node: Any) -> Any:
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            yield from _walk_bash_nodes(item)
        return
    if not hasattr(node, "kind"):
        return

    yield node
    parts = getattr(node, "parts", None)
    if isinstance(parts, list):
        for child in parts:
            yield from _walk_bash_nodes(child)


def _extract_executables_shlex_fallback(script: str) -> tuple[str, ...]:
    script = _strip_heredoc_bodies(script)
    commands: list[str] = []
    for segment in re.split(r"\|\||&&|[;\n|]", script):
        segment = segment.strip()
        if not segment:
            continue
        if segment.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", segment):
            continue
        if any(ch in segment for ch in ("'", '"', "\\", "$", "`")):
            try:
                tokens = shlex.split(segment, posix=True)
            except ValueError:
                tokens = segment.split()
        else:
            tokens = segment.split()
        if not tokens:
            continue
        command = _command_word_from_tokens(tokens)
        if command:
            commands.append(command)
    return tuple(commands)


def _strip_heredoc_bodies(script: str) -> str:
    if "<<" not in script:
        return script

    lines = script.splitlines()
    cleaned: list[str] = []
    pending_delimiters: list[str] = []

    for line in lines:
        stripped = line.strip()
        if pending_delimiters:
            if stripped == pending_delimiters[-1]:
                pending_delimiters.pop()
            continue

        cleaned.append(line)
        for _, delimiter in HEREDOC_START_RE.findall(line):
            pending_delimiters.append(delimiter)

    return "\n".join(cleaned)


@lru_cache(maxsize=200_000)
def _extract_executables(script: str) -> tuple[str, ...]:
    script = script.strip()
    if not script:
        return ()
    if len(script) > 40_000:
        return ()
    if not any(ch in script for ch in ("|", "&", ";", "\n", "'", '"', "\\", "$", "`", "(", ")", "<", ">")):
        command = _command_word_from_tokens(script.split())
        return (command,) if command else ()

    if bashlex is None:
        return _extract_executables_shlex_fallback(script)

    lowered = f" {script.lower()} "
    needs_bashlex = ("\n" in script) or any(marker in script for marker in ("$(", "`", "<<", "<(", ">(")) or any(
        control in lowered
        for control in (" for ", " while ", " until ", " if ", " then ", " do ", " done ", " case ", " function ")
    )
    if not needs_bashlex:
        return _extract_executables_shlex_fallback(script)

    try:
        trees = bashlex.parse(script)
    except Exception:  # noqa: BLE001
        return _extract_executables_shlex_fallback(script)

    commands: list[str] = []
    for tree in trees:
        for node in _walk_bash_nodes(tree):
            if getattr(node, "kind", None) != "command":
                continue
            words = [
                part.word
                for part in getattr(node, "parts", [])
                if getattr(part, "kind", None) == "word" and isinstance(getattr(part, "word", None), str)
            ]
            command = _command_word_from_tokens(words)
            if command:
                commands.append(command)

    if not commands:
        return _extract_executables_shlex_fallback(script)

    return tuple(commands)


@lru_cache(maxsize=200_000)
def _extract_skills(script: str) -> tuple[str, ...]:
    if not script:
        return ()
    found: set[str] = set()
    for match in SKILL_PATH_RE.finditer(script):
        skill = match.group("skill").strip().strip("\"'`")
        skill = skill.lstrip("./")
        if skill:
            found.add(skill)
    return tuple(sorted(found))


def _contains_any(haystack: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in haystack for pattern in patterns)


def _is_web_tool_name(tool_name: str) -> bool:
    lowered = tool_name.lower()
    return (
        tool_name in WEB_TOOLS
        or lowered.startswith(WEB_TOOL_PREFIXES)
        or "devtools" in lowered
        or "playwright" in lowered
        or lowered in {"read_mcp_resource", "list_mcp_resources"}
    )


def _is_web_shell_command(command_text: str, label: str | None, executables: tuple[str, ...]) -> bool:
    lowered = command_text.lower()
    if "http://" in lowered or "https://" in lowered or "ws://" in lowered or "wss://" in lowered:
        return True
    if label and label.lower() in WEB_EXECUTABLES:
        return True
    return any(executable.lower() in WEB_EXECUTABLES for executable in executables)


def _classify_shell_command(command_text: str, command_label: str | None) -> set[str]:
    text = f"{command_text} {command_label or ''}".lower()
    categories: set[str] = set()
    if not text.strip():
        return categories

    if _contains_any(text, TEST_COMMAND_PATTERNS):
        categories.add("test")
    if _contains_any(text, LINT_COMMAND_PATTERNS):
        categories.add("lint")
    if _contains_any(text, BUILD_COMMAND_PATTERNS):
        categories.add("build")
    if categories:
        categories.add("verification")
    if _contains_any(text, GIT_COMMAND_PATTERNS):
        categories.add("git")
    if _contains_any(text, COMMIT_COMMAND_PATTERNS):
        categories.add("commit")
    if _contains_any(text, PR_COMMAND_PATTERNS):
        categories.add("pr")
    return categories


def _format_ratio(numerator: float, denominator: float, decimals: int = 4) -> str:
    if denominator <= 0:
        return "0"
    return f"{(numerator / denominator):.{decimals}f}"


def _delta_seconds(start: datetime | None, end: datetime | None) -> str:
    if not start or not end:
        return "0"
    return str(max(0, int((end - start).total_seconds())))


def _prompt_features(text: str) -> dict[str, str]:
    normalized = _normalize(text)
    if not normalized:
        return {
            "prompt_has_file_paths": "0",
            "prompt_has_constraints": "0",
            "prompt_has_acceptance_criteria": "0",
            "prompt_has_numbered_steps": "0",
            "prompt_has_agents_md": "0",
            "prompt_has_plans_md": "0",
            "prompt_minimal_style": "0",
        }

    lowered = normalized.lower()
    word_count = len(normalized.split())
    return {
        "prompt_has_file_paths": "1" if PATH_HINT_RE.search(text) else "0",
        "prompt_has_constraints": "1" if _contains_any(lowered, CONSTRAINT_KEYWORDS) else "0",
        "prompt_has_acceptance_criteria": "1" if _contains_any(lowered, ACCEPTANCE_KEYWORDS) else "0",
        "prompt_has_numbered_steps": "1" if NUMBERED_STEP_RE.search(text) else "0",
        "prompt_has_agents_md": "1" if "agents.md" in lowered else "0",
        "prompt_has_plans_md": "1"
        if any(marker in lowered for marker in ("plan.md", "plans.md", "execplan"))
        else "0",
        "prompt_minimal_style": "1" if len(normalized) <= 800 and word_count <= 140 else "0",
    }


def _workflow_mode(objective: str, apply_patch_count: int) -> str:
    lowered = objective.lower()
    if any(keyword in lowered for keyword in ("review", "audit", "code review", "pr feedback")):
        return "code_review"
    if any(keyword in lowered for keyword in ("fix", "bug", "broken", "debug", "failing")):
        return "bugfix_debug"
    if any(keyword in lowered for keyword in ("refactor", "rewrite", "migrate", "cleanup")):
        return "refactor_migration"
    if any(keyword in lowered for keyword in ("performance", "optimize", "latency", "faster")):
        return "performance_optimization"
    if any(keyword in lowered for keyword in ("test", "coverage", "unit test", "integration test")):
        return "test_improvement"
    if any(keyword in lowered for keyword in ("docs", "documentation", "readme")):
        return "documentation"
    if any(keyword in lowered for keyword in ("understand", "inspect", "explore", "analyze")) and apply_patch_count == 0:
        return "codebase_understanding"
    if any(keyword in lowered for keyword in ("build", "create", "implement", "new feature", "scaffold")):
        return "feature_delivery"
    if any(keyword in lowered for keyword in ("deploy", "ci", "infra", "devops", "pipeline")):
        return "ops_automation"
    return "general_coding"


def _workflow_phase_tags(
    plan_update_count: int,
    tool_call_count: int,
    apply_patch_count: int,
    verification_command_count: int,
    commit_command_count: int,
    pr_command_count: int,
    subagent_spawn_count: int,
    uses_web: bool,
) -> str:
    phases: list[str] = []
    if plan_update_count > 0:
        phases.append("planned")
    if tool_call_count > 0 and apply_patch_count == 0:
        phases.append("explore")
    if apply_patch_count > 0:
        phases.append("implement")
    if verification_command_count > 0:
        phases.append("verify")
    if commit_command_count > 0 or pr_command_count > 0:
        phases.append("handoff")
    if subagent_spawn_count > 0:
        phases.append("delegate")
    if uses_web:
        phases.append("research")
    return "|".join(phases) if phases else "none"


def _patch_files(patch_text: str) -> set[str]:
    return {match.strip() for match in PATCH_FILE_RE.findall(patch_text) if match.strip()}


def _intent_tags(objective: str, tools: set[str]) -> list[str]:
    lowered = objective.lower()
    tags: list[str] = []

    for tag, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            tags.append(tag)

    if "apply_patch" in tools and "feature" not in tags and "bugfix" not in tags and "refactor" not in tags:
        tags.append("code_edit")

    if not tags:
        tags.append("general")

    return tags[:6]


def _format_top(counter: Counter[str], limit: int = 8) -> str:
    parts = [f"{name}:{count}" for name, count in counter.most_common(limit)]
    return "|".join(parts)


def _iter_records(path: Path) -> Any:
    if path.suffix == ".jsonl":
        with path.open("rb") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                parsed = _safe_json_loads(line)
                if isinstance(parsed, dict):
                    yield parsed
        return

    data = _safe_json_loads(path.read_bytes())
    if not isinstance(data, dict):
        return

    session = data.get("session")
    if isinstance(session, dict):
        yield {
            "timestamp": session.get("timestamp"),
            "type": "session_meta",
            "payload": session,
        }

    items = data.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            yield {
                "timestamp": item.get("timestamp"),
                "type": "response_item",
                "payload": item,
            }


def _fallback_timestamp(path: Path) -> str:
    stat = path.stat()
    dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _finalize_row(row: dict[str, str], path: Path) -> dict[str, str]:
    if _is_empty(row.get("session_id")):
        stem = path.stem
        row["session_id"] = stem.replace("rollout-", "", 1) if stem.startswith("rollout-") else stem

    if _is_empty(row.get("started_at")):
        row["started_at"] = _fallback_timestamp(path)
    if _is_empty(row.get("ended_at")):
        row["ended_at"] = row["started_at"]
    if _is_empty(row.get("date")):
        row["date"] = row["started_at"][:10]
    if _is_empty(row.get("duration_seconds")):
        row["duration_seconds"] = "0"

    for column in NUMERIC_COLUMNS:
        if _is_empty(row.get(column)):
            row[column] = "0"
    for column in TEXT_NONE_COLUMNS:
        if _is_empty(row.get(column)):
            row[column] = "none"
    for column in TEXT_UNKNOWN_COLUMNS:
        if _is_empty(row.get(column)):
            row[column] = "general_coding" if column == "workflow_mode" else "unknown"
    for column in BOOL_COLUMNS:
        if _is_empty(row.get(column)):
            row[column] = "0"

    if _is_empty(row.get("first_user_preview")):
        row["first_user_preview"] = "-"
    if _is_empty(row.get("objective_preview")):
        row["objective_preview"] = row["first_user_preview"]
    if _is_empty(row.get("intent_tags")):
        row["intent_tags"] = "general"
    if _is_empty(row.get("parse_status")):
        row["parse_status"] = "ok"
    if _is_empty(row.get("parse_error")):
        row["parse_error"] = "-" if row["parse_status"] == "ok" else "unknown"
    if _is_empty(row.get("is_subagent")):
        row["is_subagent"] = "0"
    if _is_empty(row.get("tagger_version")):
        row["tagger_version"] = TAGGER_VERSION
    if _is_empty(row.get("tagged_at")):
        row["tagged_at"] = _utc_now_iso()

    for column in REQUIRED_COLUMNS:
        if column not in row:
            row[column] = ""

    return row


def _analyze_session(path: Path, session_key: str) -> dict[str, str]:
    row = {column: "" for column in REQUIRED_COLUMNS}
    row["session_key"] = session_key
    row["session_file"] = str(path)
    row["session_format"] = path.suffix.lstrip(".")
    row["file_size_bytes"] = str(path.stat().st_size)
    row["parse_status"] = "ok"
    row["tagger_version"] = TAGGER_VERSION
    row["tagged_at"] = _utc_now_iso()

    event_count = 0
    first_timestamp = ""
    last_timestamp = ""
    session_timestamp = ""
    user_messages = 0
    assistant_messages = 0
    developer_messages = 0
    other_messages = 0
    total_user_chars = 0
    max_user_chars = 0
    first_user_message = ""
    objective_message = ""
    tool_calls = 0
    tool_outputs = 0
    tool_success = 0
    tool_failure = 0
    apply_patch_count = 0
    reasoning_count = 0
    plan_update_count = 0
    subagent_spawn_count = 0
    parallel_tool_call_count = 0

    verification_command_count = 0
    lint_command_count = 0
    test_command_count = 0
    build_command_count = 0
    git_command_count = 0
    commit_command_count = 0
    pr_command_count = 0

    tool_counter: Counter[str] = Counter()
    tool_failure_counter: Counter[str] = Counter()
    shell_counter: Counter[str] = Counter()
    skill_counter: Counter[str] = Counter()
    executable_counter: Counter[str] = Counter()
    edited_files: set[str] = set()
    pending_calls: dict[str, str] = {}
    seen_outputs: set[str] = set()

    tool_duration_total_seconds = 0.0
    tool_duration_count = 0
    shell_outputs = 0
    shell_failures = 0
    apply_patch_outputs = 0
    apply_patch_successes = 0
    has_web_shell_activity = False

    first_tool_dt: datetime | None = None
    first_edit_dt: datetime | None = None
    first_plan_dt: datetime | None = None
    first_verification_dt: datetime | None = None

    token_input_total = 0
    token_output_total = 0
    token_total = 0
    token_cached_input = 0

    for record in _iter_records(path):
        event_count += 1

        timestamp = record.get("timestamp")
        record_dt = _parse_iso(timestamp) if isinstance(timestamp, str) else None
        if isinstance(timestamp, str) and timestamp:
            if not first_timestamp:
                first_timestamp = timestamp
            last_timestamp = timestamp

        record_type = record.get("type")
        payload = record.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        if record_type == "session_meta":
            session_id = payload.get("id")
            if isinstance(session_id, str):
                row["session_id"] = session_id
            if isinstance(payload.get("timestamp"), str):
                session_timestamp = payload["timestamp"]
            if isinstance(payload.get("cwd"), str):
                row["cwd"] = payload["cwd"]
            if isinstance(payload.get("cli_version"), str):
                row["cli_version"] = payload["cli_version"]
            if isinstance(payload.get("model_provider"), str):
                row["model_provider"] = payload["model_provider"]
            if isinstance(payload.get("model"), str):
                row["model"] = payload["model"]
            source = payload.get("source")
            if isinstance(source, dict) and "subagent" in source:
                row["is_subagent"] = "1"
            continue

        if record_type == "turn_context":
            if isinstance(payload.get("approval_policy"), str):
                row["approval_policy"] = payload["approval_policy"]
            if not row["model"] and isinstance(payload.get("model"), str):
                row["model"] = payload["model"]
            continue

        if record_type == "event_msg":
            payload_type = payload.get("type")
            if payload_type == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    total_usage = info.get("total_token_usage")
                    if isinstance(total_usage, dict):
                        token_input_total = max(
                            token_input_total, _safe_int(total_usage.get("input_tokens"))
                        )
                        token_output_total = max(
                            token_output_total, _safe_int(total_usage.get("output_tokens"))
                        )
                        token_total = max(token_total, _safe_int(total_usage.get("total_tokens")))
                        token_cached_input = max(
                            token_cached_input, _safe_int(total_usage.get("cached_input_tokens"))
                        )
            continue

        if record_type != "response_item":
            continue

        payload_type = payload.get("type")
        if payload_type == "message":
            role = payload.get("role")
            text = _extract_message_text(payload.get("content"))
            if role == "user":
                user_messages += 1
                text_len = len(text)
                total_user_chars += text_len
                max_user_chars = max(max_user_chars, text_len)
                cleaned_text = _strip_prompt_scaffolding(text)
                if not first_user_message:
                    first_user_message = cleaned_text or text
                if cleaned_text and not objective_message:
                    objective_message = cleaned_text
                elif text and not objective_message and not _is_scaffolding_message(text):
                    objective_message = text
            elif role == "assistant":
                assistant_messages += 1
            elif role == "developer":
                developer_messages += 1
            else:
                other_messages += 1
            continue

        if payload_type in {"function_call", "custom_tool_call"}:
            tool_calls += 1
            tool_name = payload.get("name")
            if not isinstance(tool_name, str):
                tool_name = "unknown"
            tool_counter[tool_name] += 1
            if first_tool_dt is None and record_dt is not None:
                first_tool_dt = record_dt

            call_id = payload.get("call_id")
            if isinstance(call_id, str):
                pending_calls[call_id] = tool_name

            if tool_name == "update_plan":
                plan_update_count += 1
                if first_plan_dt is None and record_dt is not None:
                    first_plan_dt = record_dt
            if tool_name == "spawn_agent":
                subagent_spawn_count += 1
            if tool_name == "parallel":
                parallel_tool_call_count += 1

            if tool_name in {"exec_command", "shell"}:
                arguments = payload.get("arguments")
                label = _shell_command_label(tool_name, arguments)
                shell_counter[label or "unknown"] += 1
                command_text = _shell_command_text(tool_name, arguments)
                for skill in _extract_skills(command_text):
                    skill_counter[skill] += 1
                executables = _extract_executables(command_text)
                if executables:
                    for executable in executables:
                        executable_counter[executable] += 1
                elif label:
                    executable_counter[label] += 1
                if _is_web_shell_command(command_text, label, executables):
                    has_web_shell_activity = True
                categories = _classify_shell_command(command_text, label)
                if "verification" in categories:
                    verification_command_count += 1
                    if first_verification_dt is None and record_dt is not None:
                        first_verification_dt = record_dt
                if "lint" in categories:
                    lint_command_count += 1
                if "test" in categories:
                    test_command_count += 1
                if "build" in categories:
                    build_command_count += 1
                if "git" in categories:
                    git_command_count += 1
                if "commit" in categories:
                    commit_command_count += 1
                if "pr" in categories:
                    pr_command_count += 1

            patch_text = ""
            if tool_name == "apply_patch":
                apply_patch_count += 1
                if first_edit_dt is None and record_dt is not None:
                    first_edit_dt = record_dt
                if payload_type == "custom_tool_call":
                    patch_input = payload.get("input")
                    if isinstance(patch_input, str):
                        patch_text = patch_input
                else:
                    arguments = _safe_json_loads(payload.get("arguments"))
                    if isinstance(arguments, dict):
                        patch_input = arguments.get("input")
                        if isinstance(patch_input, str):
                            patch_text = patch_input
                if patch_text:
                    edited_files.update(_patch_files(patch_text))
            continue

        if payload_type in {"function_call_output", "custom_tool_call_output"}:
            call_id = payload.get("call_id")
            if isinstance(call_id, str):
                if call_id in seen_outputs:
                    continue
                seen_outputs.add(call_id)
            tool_outputs += 1
            succeeded, duration_seconds = _analyze_tool_output(payload.get("output"))
            if payload.get("status") == "failed":
                succeeded = False
            if duration_seconds > 0:
                tool_duration_total_seconds += duration_seconds
                tool_duration_count += 1

            output_tool_name = pending_calls.get(call_id, "unknown") if isinstance(call_id, str) else "unknown"
            if succeeded:
                tool_success += 1
            else:
                tool_failure += 1
                tool_failure_counter[output_tool_name] += 1

            if output_tool_name in {"exec_command", "shell"}:
                shell_outputs += 1
                if not succeeded:
                    shell_failures += 1
            if output_tool_name == "apply_patch":
                apply_patch_outputs += 1
                if succeeded:
                    apply_patch_successes += 1
            continue

        if payload_type == "reasoning":
            reasoning_count += 1

    objective_message = objective_message or first_user_message
    normalized_first_user = _truncate(_normalize(first_user_message))
    normalized_objective = _truncate(_normalize(objective_message))

    started_at = session_timestamp or first_timestamp
    ended_at = last_timestamp or started_at
    row["started_at"] = started_at
    row["ended_at"] = ended_at
    row["date"] = started_at[:10] if started_at else ""

    start_dt = _parse_iso(started_at)
    end_dt = _parse_iso(ended_at)
    duration_seconds = ""
    duration_seconds_int = 0
    if start_dt and end_dt:
        duration_seconds_int = max(0, int((end_dt - start_dt).total_seconds()))
        duration_seconds = str(duration_seconds_int)
    duration_minutes = duration_seconds_int / 60.0 if duration_seconds_int > 0 else 0.0

    tools_used = sorted(tool_counter)
    intents = _intent_tags(objective_message, set(tools_used))
    prompt_features = _prompt_features(objective_message)
    workflow_mode = _workflow_mode(objective_message, apply_patch_count)
    uses_web = any(_is_web_tool_name(name) for name in tool_counter) or has_web_shell_activity
    workflow_phase_tags = _workflow_phase_tags(
        plan_update_count=plan_update_count,
        tool_call_count=tool_calls,
        apply_patch_count=apply_patch_count,
        verification_command_count=verification_command_count,
        commit_command_count=commit_command_count,
        pr_command_count=pr_command_count,
        subagent_spawn_count=subagent_spawn_count,
        uses_web=uses_web,
    )
    files_edited_count = len(edited_files)
    plan_before_edit = bool(
        first_plan_dt is not None and first_edit_dt is not None and first_plan_dt <= first_edit_dt
    )
    verification_after_edit = bool(
        first_verification_dt is not None and first_edit_dt is not None and first_verification_dt >= first_edit_dt
    )

    row["event_count"] = str(event_count)
    row["duration_seconds"] = duration_seconds
    row["user_message_count"] = str(user_messages)
    row["assistant_message_count"] = str(assistant_messages)
    row["developer_message_count"] = str(developer_messages)
    row["other_message_count"] = str(other_messages)
    row["first_user_chars"] = str(len(objective_message))
    row["first_user_preview"] = normalized_first_user
    row["objective_preview"] = normalized_objective
    row["total_user_chars"] = str(total_user_chars)
    row["max_user_chars"] = str(max_user_chars)
    row["tool_call_count"] = str(tool_calls)
    row["tool_output_count"] = str(tool_outputs)
    row["tool_success_count"] = str(tool_success)
    row["tool_failure_count"] = str(tool_failure)
    row["has_tool_failures"] = "1" if tool_failure else "0"
    row["tool_error_rate"] = _format_ratio(tool_failure, tool_outputs)
    row["tools_used"] = "|".join(tools_used)
    row["top_tools"] = _format_top(tool_counter)
    row["top_failing_tools"] = _format_top(tool_failure_counter)
    row["shell_command_count"] = str(sum(shell_counter.values()))
    row["shell_error_rate"] = _format_ratio(shell_failures, shell_outputs)
    row["command_diversity"] = str(len(shell_counter))
    row["top_shell_commands"] = _format_top(shell_counter)
    row["skill_count"] = str(len(skill_counter))
    row["skills_used"] = "|".join(sorted(skill_counter))
    row["top_skills"] = _format_top(skill_counter)
    row["executable_count"] = str(len(executable_counter))
    row["executables_used"] = "|".join(sorted(executable_counter))
    row["top_executables"] = _format_top(executable_counter)
    row["tool_duration_total_seconds"] = f"{tool_duration_total_seconds:.3f}" if tool_duration_total_seconds else "0"
    row["tool_duration_avg_seconds"] = _format_ratio(tool_duration_total_seconds, tool_duration_count, 3)
    row["time_to_first_tool_seconds"] = _delta_seconds(start_dt, first_tool_dt)
    row["time_to_first_edit_seconds"] = _delta_seconds(start_dt, first_edit_dt)
    row["time_to_first_verification_seconds"] = _delta_seconds(start_dt, first_verification_dt)
    row["apply_patch_count"] = str(apply_patch_count)
    row["apply_patch_success_rate"] = _format_ratio(apply_patch_successes, apply_patch_outputs)
    row["files_edited_count"] = str(files_edited_count)
    row["files_per_patch"] = _format_ratio(files_edited_count, apply_patch_count)
    row["files_edited"] = "|".join(sorted(edited_files))
    row["tool_calls_per_minute"] = _format_ratio(tool_calls, duration_minutes)
    row["edits_per_minute"] = _format_ratio(apply_patch_count, duration_minutes)
    row["feature_exec_command"] = "1" if any(name in tool_counter for name in {"exec_command", "shell"}) else "0"
    row["feature_apply_patch"] = "1" if "apply_patch" in tool_counter else "0"
    row["feature_update_plan"] = "1" if "update_plan" in tool_counter else "0"
    row["feature_subagents"] = "1" if any(name in tool_counter for name in SUBAGENT_TOOLS) else "0"
    row["feature_parallel"] = "1" if "parallel" in tool_counter else "0"
    row["feature_web"] = "1" if uses_web else "0"
    row["feature_image"] = "1" if any(name in tool_counter for name in IMAGE_TOOLS) else "0"
    row["reasoning_count"] = str(reasoning_count)
    row["token_input_total"] = str(token_input_total)
    row["token_output_total"] = str(token_output_total)
    row["token_total"] = str(token_total)
    row["token_cached_input"] = str(token_cached_input)
    row["plan_update_count"] = str(plan_update_count)
    row["plan_before_edit"] = "1" if plan_before_edit else "0"
    row["subagent_spawn_count"] = str(subagent_spawn_count)
    row["parallel_tool_call_count"] = str(parallel_tool_call_count)
    row["verification_command_count"] = str(verification_command_count)
    row["verification_after_edit"] = "1" if verification_after_edit else "0"
    row["verification_commands_per_edit"] = _format_ratio(verification_command_count, apply_patch_count)
    row["lint_command_count"] = str(lint_command_count)
    row["test_command_count"] = str(test_command_count)
    row["build_command_count"] = str(build_command_count)
    row["git_command_count"] = str(git_command_count)
    row["commit_command_count"] = str(commit_command_count)
    row["pr_command_count"] = str(pr_command_count)
    row.update(prompt_features)
    row["workflow_mode"] = workflow_mode
    row["workflow_phase_tags"] = workflow_phase_tags
    row["intent_tags"] = "|".join(intents)

    return _finalize_row(row, path)


def _error_row(path: Path, session_key: str, error: Exception) -> dict[str, str]:
    row = {column: "" for column in REQUIRED_COLUMNS}
    row["session_key"] = session_key
    row["session_file"] = str(path)
    row["session_format"] = path.suffix.lstrip(".")
    row["file_size_bytes"] = str(path.stat().st_size)
    row["parse_status"] = "error"
    row["parse_error"] = _truncate(_normalize(str(error)), 400)
    row["tagger_version"] = TAGGER_VERSION
    row["tagged_at"] = _utc_now_iso()
    row["is_subagent"] = "0"
    return _finalize_row(row, path)


def _process_one_session(task: tuple[str, str]) -> tuple[str, dict[str, str]]:
    key, path_str = task
    path = Path(path_str)
    try:
        return key, _analyze_session(path, key)
    except Exception as exc:  # noqa: BLE001
        return key, _error_row(path, key, exc)


def _load_existing_rows(csv_path: Path, sessions_root: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    if not csv_path.exists():
        return {}, []

    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows: dict[str, dict[str, str]] = {}
        root_resolved = sessions_root.resolve()

        for raw_row in reader:
            row = {key: (value or "") for key, value in raw_row.items()}
            key = row.get("session_key", "").strip()
            if not key:
                session_file = row.get("session_file", "").strip()
                if session_file:
                    try:
                        key = str(Path(session_file).resolve().relative_to(root_resolved))
                    except ValueError:
                        key = Path(session_file).name
            if key:
                rows[key] = row

    return rows, headers


def _discover_sessions(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix == ".jsonl" and path.name != "tags.csv"
    )


def _should_process(row: dict[str, str] | None, force: bool) -> bool:
    if force or row is None:
        return True
    return any(_is_empty(row.get(column)) for column in REQUIRED_COLUMNS)


def _merge_rows(existing: dict[str, str] | None, computed: dict[str, str], force: bool) -> dict[str, str]:
    if not existing:
        return computed.copy()

    merged = existing.copy()
    for column in REQUIRED_COLUMNS:
        value = computed.get(column, "")
        if force or _is_empty(merged.get(column)):
            merged[column] = value

    merged["session_key"] = computed["session_key"]
    merged["session_file"] = computed["session_file"]
    return merged


def _build_headers(existing_headers: list[str]) -> list[str]:
    headers: list[str] = []
    for column in REQUIRED_COLUMNS + existing_headers:
        if column and column not in headers:
            headers.append(column)
    return headers


def _write_csv(csv_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = csv_path.with_suffix(f"{csv_path.suffix}.tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in headers})
    tmp_path.replace(csv_path)


def update_tags(
    sessions_root: Path,
    tags_csv: Path,
    force: bool = False,
    jobs: int = 0,
    limit: int = 0,
) -> UpdateSummary:
    sessions = _discover_sessions(sessions_root)
    if limit > 0:
        sessions = sessions[:limit]

    existing_rows, existing_headers = _load_existing_rows(tags_csv, sessions_root)
    root_resolved = sessions_root.resolve()

    queued: list[tuple[str, Path]] = []
    skipped = 0
    for path in sessions:
        key = str(path.resolve().relative_to(root_resolved))
        row = existing_rows.get(key)
        if _should_process(row, force=force):
            queued.append((key, path))
        else:
            skipped += 1

    computed_rows: dict[str, dict[str, str]] = {}
    parse_errors = 0

    if queued:
        workers = jobs if jobs > 0 else min(32, max(2, (os.cpu_count() or 4)))
        if workers <= 1 or len(queued) == 1:
            for key, path in queued:
                row = _process_one_session((key, str(path)))[1]
                if row.get("parse_status") == "error":
                    parse_errors += 1
                computed_rows[key] = row
        else:
            executor_cls = ProcessPoolExecutor if len(queued) >= 200 else ThreadPoolExecutor
            with executor_cls(max_workers=workers) as pool:
                futures = {
                    pool.submit(_process_one_session, (key, str(path))): key for key, path in queued
                }
                for future in as_completed(futures):
                    key, row = future.result()
                    if row.get("parse_status") == "error":
                        parse_errors += 1
                    computed_rows[key] = row

    merged_rows: list[dict[str, str]] = []
    for path in sessions:
        key = str(path.resolve().relative_to(root_resolved))
        existing = existing_rows.get(key)
        computed = computed_rows.get(key)
        if computed is not None:
            merged_rows.append(_merge_rows(existing, computed, force=force))
        elif existing is not None:
            merged = existing.copy()
            merged["session_key"] = key
            merged["session_file"] = str(path)
            merged_rows.append(merged)

    headers = _build_headers(existing_headers)
    _write_csv(tags_csv, headers, merged_rows)

    return UpdateSummary(
        total_sessions=len(sessions),
        queued_sessions=len(queued),
        processed_sessions=len(computed_rows),
        skipped_sessions=skipped,
        parse_errors=parse_errors,
    )


@app.command()
def main(
    sessions_root: Path = typer.Argument(
        Path.home() / ".codex/sessions",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
        help="Session root containing .json/.jsonl files.",
    ),
    tags_csv: Path | None = typer.Option(
        None,
        "--tags-csv",
        help="Output CSV path (default: <sessions_root>/tags.csv).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Recompute all known tags for all sessions.",
    ),
    jobs: int = typer.Option(
        0,
        "--jobs",
        min=0,
        help="Parallel worker count. 0 = auto.",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        min=0,
        help="Process only the first N sessions (for debugging).",
    ),
) -> None:
    output_csv = tags_csv or (sessions_root / "tags.csv")
    summary = update_tags(
        sessions_root=sessions_root,
        tags_csv=output_csv,
        force=force,
        jobs=jobs,
        limit=limit,
    )

    typer.echo(
        "sessions={total} queued={queued} processed={processed} skipped={skipped} parse_errors={errors}".format(
            total=summary.total_sessions,
            queued=summary.queued_sessions,
            processed=summary.processed_sessions,
            skipped=summary.skipped_sessions,
            errors=summary.parse_errors,
        )
    )
    typer.echo(f"wrote {output_csv}")


if __name__ == "__main__":
    app()
