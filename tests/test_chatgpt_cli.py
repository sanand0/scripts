from __future__ import annotations

import asyncio
import importlib.util
import importlib.machinery
import json
import sys
from pathlib import Path

import pytest
from playwright.async_api import async_playwright
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
    assert chatgpt.chat_url(None, temporary=True) == "https://chatgpt.com/?temporary-chat=true"
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


def test_save_path_defaults_to_timestamped_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDatetime:
        @classmethod
        def now(cls) -> object:
            class Value:
                def strftime(self, _: str) -> str:
                    return "2026-06-26-12-34-56"

            return Value()

    monkeypatch.setattr(chatgpt, "datetime", FrozenDatetime)

    assert chatgpt.save_path(None) == Path.cwd() / "chatgpt-2026-06-26-12-34-56.txt"
    assert chatgpt.save_path(tmp_path) == tmp_path / "chatgpt-2026-06-26-12-34-56.txt"
    assert chatgpt.save_path(tmp_path / "answer.md") == tmp_path / "answer.md"


def test_saved_markdown_includes_link_prompt_and_response() -> None:
    markdown = chatgpt.saved_markdown("https://chatgpt.com/c/abc", "Question?", "# Answer\n")

    assert markdown == (
        "---\n"
        "link: https://chatgpt.com/c/abc\n"
        "---\n"
        "\n"
        "## User\n"
        "\n"
        "Question?\n"
        "\n"
        "## ChatGPT\n"
        "\n"
        "# Answer\n"
    )


def test_copy_response_waits_for_assistant_turn() -> None:
    async def run() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(
                """
                <main>
                  <section data-testid="conversation-turn-0">
                    <div data-message-author-role="assistant">stale assistant text</div>
                    <button data-testid="copy-turn-action-button" aria-label="Copy response"
                      onclick="window.__copied = 'stale assistant text'"></button>
                  </section>
                  <section data-testid="conversation-turn-1">
                    <div data-message-author-role="user">prompt text</div>
                    <button data-testid="copy-turn-action-button" aria-label="Copy message"
                      onclick="window.__copied = 'prompt text'"></button>
                  </section>
                </main>
                <script>
                Object.defineProperty(navigator, 'clipboard', {
                  value: {readText: async () => window.__copied || ''}
                });
                setTimeout(() => {
                  document.querySelector('main').insertAdjacentHTML('beforeend', `
                    <section data-testid="conversation-turn-2">
                      <div data-message-author-role="assistant">assistant text</div>
                      <button data-testid="copy-turn-action-button" aria-label="Copy response"
                        onclick="window.__copied = 'assistant text'"></button>
                    </section>
                  `);
                }, 100);
                </script>
                """
            )
            try:
                return await chatgpt.copy_response_markdown(page, "prompt text")
            finally:
                await browser.close()

    assert asyncio.run(run()) == "assistant text"


def test_copy_response_falls_back_when_clipboard_stays_stale() -> None:
    async def run() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(
                """
                <main>
                  <section data-testid="conversation-turn-1">
                    <div data-message-author-role="user">prompt text</div>
                  </section>
                  <section data-testid="conversation-turn-2">
                    <div data-message-author-role="assistant">fresh assistant text</div>
                    <button data-testid="copy-turn-action-button" aria-label="Copy response"></button>
                  </section>
                </main>
                <script>
                Object.defineProperty(navigator, 'clipboard', {
                  value: {readText: async () => 'stale clipboard text'}
                });
                </script>
                """
            )
            try:
                return await chatgpt.copy_response_markdown(page, "prompt text")
            finally:
                await browser.close()

    assert asyncio.run(run()) == "fresh assistant text"


def test_copy_response_fallback_waits_for_stable_assistant_text() -> None:
    async def run() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(
                """
                <main>
                  <section data-testid="conversation-turn-1">
                    <div data-message-author-role="user">prompt text</div>
                  </section>
                  <section data-testid="conversation-turn-2">
                    <div data-message-author-role="assistant" id="answer">fresh</div>
                    <button data-testid="copy-turn-action-button" aria-label="Copy response"></button>
                  </section>
                </main>
                <script>
                Object.defineProperty(navigator, 'clipboard', {
                  value: {readText: async () => 'stale clipboard text'}
                });
                setTimeout(() => {
                  document.querySelector('#answer').textContent = 'fresh assistant text';
                }, 300);
                </script>
                """
            )
            try:
                return await chatgpt.copy_response_markdown(page, "prompt text")
            finally:
                await browser.close()

    assert asyncio.run(run()) == "fresh assistant text"


def test_normalize_save_args_allows_optional_target() -> None:
    assert chatgpt.normalize_save_args(["--save"]) == ["--save", "."]
    assert chatgpt.normalize_save_args(["--save", "--model", "gpt-5"]) == ["--save", ".", "--model", "gpt-5"]
    assert chatgpt.normalize_save_args(["--save", "out.md"]) == ["--save", "out.md"]
    assert chatgpt.normalize_save_args(["--save=out.md"]) == ["--save=out.md"]


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
