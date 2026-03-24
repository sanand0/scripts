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
