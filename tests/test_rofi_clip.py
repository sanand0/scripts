from __future__ import annotations

from pathlib import Path
import subprocess
import textwrap


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "rofi-clip.sh"


def run_transform(transform_name: str, text: str) -> subprocess.CompletedProcess[str]:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        INPUT="$2"
        "$3"
        """
    )
    return subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH), text, transform_name],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )


def run_shell(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )


def test_transform_text_to_slug_transliterates_and_normalizes() -> None:
    result = run_transform("transform_text_to_slug", " Peoples' Café ")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "peoples-cafe"


def test_transform_text_to_slug_collapses_runs_and_trims_edges() -> None:
    result = run_transform("transform_text_to_slug", "---Hello___world!!!---")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello-world"


def test_transform_text_to_slug_flattens_multiline_input() -> None:
    result = run_transform("transform_text_to_slug", "First line\n\nSecond line")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "first-line-second-line"


def test_transform_html_to_md_reuses_shared_helpers() -> None:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        clipboard_get_html() { printf '<p>Hello</p>'; }
        html_to_markdown() { printf 'Hello'; }
        transform_html_to_md
        """
    )

    result = subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello"


def test_transform_html_to_md_falls_back_to_plain_text_clipboard_input() -> None:
    command = textwrap.dedent(
        """\
        source "$1"
        bootstrap_tool_paths
        INPUT='<p>Hello</p>'
        clipboard_get_html() { printf ''; }
        html_to_markdown() {
            local html
            html=$(cat)
            [[ "$html" == '<p>Hello</p>' ]] || exit 1
            printf 'Hello'
        }
        transform_html_to_md
        """
    )

    result = subprocess.run(
        ["bash", "-lc", command, "bash", str(SCRIPT_PATH)],
        capture_output=True,
        text=True,
        check=False,
        cwd=SCRIPT_PATH.parent,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Hello"


def test_menu_exposes_html_to_markdown_command() -> None:
    result = run_shell(
        textwrap.dedent(
            """\
            source "$1"
            bootstrap_tool_paths
            printf '%s' "${MENU_FNS["HTML → Markdown                (from clipboard HTML)"]}"
            """
        )
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "transform_html_to_md"
