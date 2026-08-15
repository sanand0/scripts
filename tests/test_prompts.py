from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "prompt"


@pytest.fixture
def prompt_home(tmp_path: Path) -> Path:
    prompts = tmp_path / "code/blog/pages/prompts"
    prompts.mkdir(parents=True)
    (prompts / "git-commit.md").write_text(
        "---\ntitle: Git commit\ndescription: Write a commit message\n---\n\n```text\nCommit clearly.\n```\n"
    )
    (prompts / "fragments.md").write_text(
        "---\ntitle: Fragments\n---\n\n## Explain code\n\n```\nExplain this code.\n```\n\n## Review code\n\n```\nReview this code.\n```\n"
    )
    skill = tmp_path / "code/scripts/agents/code/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        '---\nname: code\ndescription: Use <simple> & "clear" code\n---\n\nKeep it clear.\n'
    )
    return tmp_path


def run_prompts(
    home: Path, *args: str, path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"HOME": str(home)}
    if path:
        env["PATH"] = f"{path}:{env['PATH']}"
    return subprocess.run(
        [str(SCRIPT), *args], text=True, capture_output=True, env=env, check=False
    )


def test_filter_prints_best_prompt_without_rofi(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "gitcommit")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Commit clearly.\n"


def test_filter_can_select_heading(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "review")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Review this code.\n"


def test_filter_includes_custom_prompts_used_by_fish(prompt_home: Path) -> None:
    custom = prompt_home / "code/scripts/agents/custom-prompts/release-note.md"
    custom.parent.mkdir(parents=True)
    custom.write_text(
        "---\ndescription: Summarize a release\n---\n\nSummarize user-visible changes.\n"
    )

    result = run_prompts(prompt_home, "release-note")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Summarize user-visible changes.\n"


def test_json_output_includes_selection_metadata(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "explain", "--format", "json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "content": "Explain this code.",
        "kind": "prompt",
        "label": "Fragments › Explain code",
        "source": str(prompt_home / "code/blog/pages/prompts/fragments.md"),
    }


def test_skill_output_preserves_body_and_escapes_description(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "skill code")

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        '<skill name="code" description="Use &lt;simple&gt; &amp; &quot;clear&quot; code">\n'
        "\nKeep it clear.\n\n</skill>\n"
    )


def test_list_jsonl_streams_machine_readable_index(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "--list", "--format", "jsonl")

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    assert [row["label"] for row in rows] == [
        "Fragments › Explain code",
        "Fragments › Review code",
        "Git commit: Write a commit message",
        'Skill › code: Use <simple> & "clear" code',
    ]


def test_interactive_selection_copies_and_logs(
    prompt_home: Path, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "rofi").write_text("#!/bin/sh\ngrep '^Git commit:'\n")
    (bin_dir / "wl-copy").write_text(f"#!/bin/sh\ncat > {tmp_path}/copied\n")
    (bin_dir / "wtype").write_text(
        f"#!/bin/sh\nprintf '%s' \"$1\" > {tmp_path}/typed\n"
    )
    for executable in bin_dir.iterdir():
        executable.chmod(0o755)

    result = run_prompts(prompt_home, path=bin_dir)

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "copied").read_text() == "Commit clearly."
    assert (tmp_path / "typed").read_text() == "Commit clearly."
    log = prompt_home / ".local/share/sanand-scripts/rofi-prompts-log.tsv"
    assert log.read_text().split("\t", 1)[1] == "Git commit: Write a commit message\n"


def test_interactive_cancellation_does_not_log(
    prompt_home: Path, tmp_path: Path
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "rofi").write_text("#!/bin/sh\ncat >/dev/null\nexit 1\n")
    (bin_dir / "rofi").chmod(0o755)

    result = run_prompts(prompt_home, path=bin_dir)

    assert result.returncode == 0, result.stderr
    assert not (
        prompt_home / ".local/share/sanand-scripts/rofi-prompts-log.tsv"
    ).exists()


def test_describe_is_json(prompt_home: Path) -> None:
    result = run_prompts(prompt_home, "--describe")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["name"] == "prompt"
