from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import importlib.machinery
import importlib.util
from typer.testing import CliRunner


def load_gmail_module() -> Any:
    """Load the gmail script as a module for testing."""
    path = Path(__file__).resolve().parents[1] / "gmail"
    loader = importlib.machinery.SourceFileLoader("gmail_mod", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def make_fake_api() -> Any:
    async def fake_api(client: Any, method: str, path: str, **kwargs) -> Dict[str, Any]:
        if path == "/messages":
            return {"messages": [{"id": "1"}]}
        if path == "/messages/1":
            return {
                "id": "1",
                "snippet": "Snippet",
                "labelIds": ["INBOX"],
                "sizeEstimate": 123,
                "payload": {
                    "headers": [
                        {"name": "From", "value": "John Doe <john@example.com>"},
                        {"name": "To", "value": "Jane <jane@example.com>"},
                        {"name": "Subject", "value": "Hello"},
                    ]
                },
            }
        raise AssertionError(f"Unexpected API call: {method} {path}")

    return fake_api


def test_email_field_and_json_output(monkeypatch):
    gmail = load_gmail_module()
    monkeypatch.setattr(gmail, "ensure_token", lambda **_: "tok")
    monkeypatch.setattr(gmail, "api", make_fake_api())

    runner = CliRunner()
    result = runner.invoke(gmail.app, ["--json", "--fields", "email,subject"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["items"] and isinstance(data["items"], list)
    row = data["items"][0]
    assert row["email"] == "john@example.com"
    assert row["subject"] == "Hello"


def test_fields_comma_space_separated(monkeypatch):
    gmail = load_gmail_module()
    monkeypatch.setattr(gmail, "ensure_token", lambda **_: "tok")
    monkeypatch.setattr(gmail, "api", make_fake_api())

    runner = CliRunner()
    # Mix of spaces and commas
    result = runner.invoke(gmail.app, ["--json", "--fields", "email subject, snippet"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    row = data["items"][0]
    assert {"email", "subject", "snippet"}.issubset(set(row.keys()))
    assert row["email"] == "john@example.com"
    assert row["snippet"] == "Snippet"
