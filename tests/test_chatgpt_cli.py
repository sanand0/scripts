from __future__ import annotations

import importlib.util
import importlib.machinery
import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("chatgpt_cli", str(ROOT / "chatgpt"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC and SPEC.loader
chatgpt = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = chatgpt
SPEC.loader.exec_module(chatgpt)

RUNNER = CliRunner()


def test_describe_is_machine_readable() -> None:
    result = RUNNER.invoke(chatgpt.app, ["--describe"])

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["name"] == "chatgpt"
    assert data["default_cdp_url"] == "http://localhost:9222"
    assert "inspect" in data["actions"]
    assert any("inspect" in example for example in data["examples"])
    assert "--dry-run" in " ".join(data["examples"])


def test_chat_url_includes_model() -> None:
    assert chatgpt.chat_url(None) == "https://chatgpt.com/"
    assert chatgpt.chat_url("gpt-5 thinking") == "https://chatgpt.com/?model=gpt-5+thinking"


def test_prompt_from_args_or_stdin() -> None:
    assert chatgpt.prompt_text(("hello", "world"), "") == "hello world"
    assert chatgpt.prompt_text((), "from stdin\n") == "from stdin"
    with pytest.raises(ValueError, match="prompt is required"):
        chatgpt.prompt_text((), "")


def test_validate_files_requires_existing_paths(tmp_path: Path) -> None:
    existing = tmp_path / "note.txt"
    existing.write_text("hello\n")

    assert chatgpt.validate_files([existing]) == [existing]
    with pytest.raises(ValueError, match="file not found"):
        chatgpt.validate_files([tmp_path / "missing.txt"])


def test_dry_run_requires_no_cdp(tmp_path: Path) -> None:
    existing = tmp_path / "note.txt"
    existing.write_text("hello\n")

    result = RUNNER.invoke(
        chatgpt.app,
        ["--dry-run", "--model", "gpt-5", "--file", str(existing), "--", "Say", "hi"],
    )

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data["submit"] is False
    assert data["prompt"] == "Say hi"
    assert data["files"] == [str(existing)]
