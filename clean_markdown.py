#!/usr/bin/env -S uv run --offline --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["typer>=0.12"]
# ///

# Usage: Press Ctrl+C to copy rich text (e.g. web page). Then press Ctrl+Alt+C to run this script.
# Clipboard now has a Markdown version of the HTML.
# See setup/media-keys.dconf for keybinding setup.

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys

LIST_RE = re.compile(r"^([ \t]*)([*+-]|\d+[.)])([ \t]+)(.*)$")
LEADING_WS_RE = re.compile(r"^[ \t]*")


def indent_len(ws: str) -> int:
    return sum(4 if c == "\t" else 1 for c in ws)


def is_blank(line: str) -> bool:
    return line.strip() == ""


def clean_markdown(text: str) -> str:
    """Remove blank lines between list items while preserving paragraph breaks."""
    lines = text.splitlines(keepends=True)
    out = []
    stack: list[dict[str, int]] = []
    total = len(lines)

    for i, line in enumerate(lines):
        if is_blank(line):
            if not stack:
                out.append(line)
                continue

            j = i + 1
            while j < total and is_blank(lines[j]):
                j += 1

            if j >= total:
                out.append(line)
                continue

            if LIST_RE.match(lines[j]):
                continue

            out.append(line)
            continue

        indent_ws = LEADING_WS_RE.match(line).group(0)
        indent = indent_len(indent_ws)

        while stack and indent < stack[-1]["content_indent"]:
            stack.pop()

        m = LIST_RE.match(line)
        if m:
            indent_ws, marker, sep, _rest = m.groups()
            content_indent = indent_len(indent_ws) + len(marker) + indent_len(sep)
            stack.append({"indent": indent_len(indent_ws), "content_indent": content_indent})

        out.append(line)

    return "".join(out)


def _require_xclip() -> None:
    if shutil.which("xclip") is None:
        raise ValueError("xclip not found in PATH.")


def _read_clipboard() -> str:
    result = subprocess.run(
        ["xclip", "-o", "-selection", "clipboard"],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _write_clipboard(text: str) -> None:
    subprocess.run(
        ["xclip", "-i", "-selection", "clipboard"],
        check=True,
        text=True,
        input=text,
    )


TEST_CASES = [
    (
        "basic",
        "- Bullets should not have empty lines INSIDE them\n\n"
        "  - This bullet has an extra line (maybe with white spaces) before this sub-bullet\n"
        "  - Next line has empty white spaces\n"
        "  \n"
        "    - This sub-sub-bullet has an extra line above it - with whitespaces\n"
        "    - Next sub-sub-bullet has an extra line below it\n\n"
        "- There's an extra line above this bullet\n",
        "- Bullets should not have empty lines INSIDE them\n"
        "  - This bullet has an extra line (maybe with white spaces) before this sub-bullet\n"
        "  - Next line has empty white spaces\n"
        "    - This sub-sub-bullet has an extra line above it - with whitespaces\n"
        "    - Next sub-sub-bullet has an extra line below it\n"
        "- There's an extra line above this bullet\n",
    ),
    (
        "paragraphs",
        "- This bullet has multiple paragraphs.\n\n"
        "  This is the second paragraph of the same bullet.\n"
        "  - This is a second-level bullet inside the first bullet.\n\n"
        "    This is a paragraph inside the second-level bullet.\n",
        "- This bullet has multiple paragraphs.\n\n"
        "  This is the second paragraph of the same bullet.\n"
        "  - This is a second-level bullet inside the first bullet.\n\n"
        "    This is a paragraph inside the second-level bullet.\n",
    ),
    (
        "outside-paragraph",
        "- One list item.\n\nOutside paragraph.\n",
        "- One list item.\n\nOutside paragraph.\n",
    ),
    (
        "ordered",
        "1. First ordered item.\n\n2. Second ordered item.\n\n   - Nested a\n     \n   - Nested b\n",
        "1. First ordered item.\n2. Second ordered item.\n   - Nested a\n   - Nested b\n",
    ),
    (
        "whitespace-only",
        "- a\n     \n   \n  - b\n",
        "- a\n  - b\n",
    ),
    (
        "code-block",
        "- Item with code block.\n\n    code line 1\n    code line 2\n",
        "- Item with code block.\n\n    code line 1\n    code line 2\n",
    ),
]


def _run_tests() -> int:
    failures = 0
    for name, input_text, expected_text in TEST_CASES:
        actual = clean_markdown(input_text)
        if actual != expected_text:
            failures += 1
            print(f"FAIL {name}", file=sys.stderr)
        else:
            print(f"PASS {name}")
    return 1 if failures else 0


def _build_app():
    import typer

    app = typer.Typer(add_completion=False)

    @app.command()
    def main(
        input_path: Path | None = typer.Argument(
            None,
            help="Markdown file to clean",
        ),
        output_path: Path | None = typer.Argument(
            None,
            help="Optional output file (defaults to stdout)",
        ),
        in_place: bool = typer.Option(
            False,
            "--in-place",
            help="Rewrite input file in place",
        ),
        xclip: bool = typer.Option(
            False,
            "--xclip",
            help="Read input from the clipboard and write output back to the clipboard",
        ),
        test: bool = typer.Option(
            False,
            "--test",
            help="Run built-in tests",
        ),
    ) -> None:
        """Normalize list formatting for a Markdown file or clipboard contents."""
        if test:
            if input_path or output_path or in_place or xclip:
                raise typer.BadParameter("Use --test by itself without other options.")
            raise typer.Exit(code=_run_tests())

        if xclip:
            if input_path or output_path or in_place:
                raise typer.BadParameter("Use --xclip by itself without file options.")
            try:
                _require_xclip()
            except ValueError as exc:
                raise typer.BadParameter(str(exc)) from exc
            cleaned = clean_markdown(_read_clipboard())
            _write_clipboard(cleaned)
            return

        if input_path is None:
            raise typer.BadParameter("INPUT is required unless --xclip is used.")
        if output_path and in_place:
            raise typer.BadParameter("Use either an output file or --in-place, not both.")

        text = input_path.read_text(encoding="utf-8")
        cleaned = clean_markdown(text)

        if in_place:
            input_path.write_text(cleaned, encoding="utf-8")
            return
        if output_path:
            output_path.write_text(cleaned, encoding="utf-8")
            return

        sys.stdout.write(cleaned)

    return app


if __name__ == "__main__":
    _build_app()()
