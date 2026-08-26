from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "fish_usage.py"
SCRIPTS = (
    "browsing_history.py",
    "call",
    "dev.sh",
    "edge",
    "git-size",
    "git-stage-repo",
    "git-uncommitted",
    "htmlemail.py",
    "mcpserver.py",
    "prompt",
    "summarize.py",
)


@pytest.fixture
def fish_home(tmp_path: Path) -> Path:
    scripts = tmp_path / "code/scripts"
    scripts.mkdir(parents=True)
    (scripts / "setup.fish").write_text("function blog\nend\n")
    for name in SCRIPTS:
        (scripts / name).write_text("#!/bin/sh\n")
    return tmp_path


def run_usage(
    home: Path, commands: list[tuple[str, int]], days: int = 90
) -> dict[str, tuple[int, str, str]]:
    history = home / ".local/share/fish/fish_history"
    history.parent.mkdir(parents=True)
    history.write_text(
        "".join(f"- cmd: {command}\n  when: {when}\n" for command, when in commands)
    )
    result = subprocess.run(
        [str(SCRIPT), str(days)],
        env=os.environ | {"HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "uses\tlast\tkind\tname"
    return {
        name: (int(uses), last, kind)
        for line in result.stdout.splitlines()[1:]
        for uses, last, kind, name in [line.split("\t")]
    }


def test_counts_real_script_invocation_shapes(fish_home: Path) -> None:
    now = int(time.time())
    commands = [
        ("blog | edge contents", now),
        ("/home/sanand/code/scripts/edge tabs --json | jaq -c '.timestamp'", now),
        ("./browsing_history.py | moor -S", now),
        ("git size --cached", now),
        ("git stage-repo wikipedia-parquet", now),
        ("git uncommitted | xclip -selection clipboard", now),
        (
            "ug -rl '^date: 2026-04' /home/sanand/code/blog/posts/ | xargs uv run summarize.py blog",
            now,
        ),
        (
            "git diff --cached | trimdiff | llm --system (prompt git-commit | string collect)",
            now,
        ),
        (
            (
                "dev.sh -v /home/sanand/code/scripts:/home/sanand/code/scripts:ro -- "
                "uv run /home/sanand/code/scripts/mcpserver.py"
            ),
            now,
        ),
        (
            (
                "dev.sh -v /home/sanand/code/scripts:/home/sanand/code/scripts:ro "
                "uv run /home/sanand/code/scripts/mcpserver.py"
            ),
            now,
        ),
    ]

    rows = run_usage(fish_home, commands)

    assert rows["blog"][0] == 1
    assert rows["edge"][0] == 2
    assert rows["browsing_history.py"][0] == 1
    assert rows["git-size"][0] == 1
    assert rows["git-stage-repo"][0] == 1
    assert rows["git-uncommitted"][0] == 1
    assert rows["summarize.py"][0] == 1
    assert rows["prompt"][0] == 1
    assert rows["dev.sh"][0] == 2
    assert rows["mcpserver.py"][0] == 2


def test_ignores_real_non_invocation_mentions(fish_home: Path) -> None:
    now = int(time.time())
    commands = [
        ("echo edge", now),
        ('echo "prompt edge summarize.py"', now),
        ("# uv run ~/code/scripts/summarize.py blog ~/code/blog/posts/2026/*.md", now),
        (
            'git commit -m"Rewrite 2026 descriptions and tags with new summarize.py"',
            now,
        ),
        ("code ~/code/scripts/edge", now),
        ("git add git-size git-stage-repo git-uncommitted", now),
        ("uv add --script htmlemail.py python-frontmatter markdown premailer", now),
        ("uv run scripts/htmlemail.py --email s-anand@googlegroups.com post.md", now),
        ('abbr --add recentblogs "find . | xargs uv run summarize.py blog"', now),
        (r"function helper\n edge contents\nend", now),
    ]

    rows = run_usage(fish_home, commands)

    for name in ("edge", "prompt", "summarize.py", "htmlemail.py"):
        assert rows[name][0] == 0


def test_respects_days_and_reports_last_use_and_kind(fish_home: Path) -> None:
    now = int(time.time())
    recent = now - 2 * 86400
    old = now - 40 * 86400

    rows = run_usage(
        fish_home,
        [("edge tabs", old), ("edge contents", recent), ("blog", recent)],
        days=30,
    )

    assert rows["edge"] == (
        1,
        time.strftime("%Y-%m-%d %H:%M", time.localtime(recent)),
        "script",
    )
    assert rows["blog"] == (
        1,
        time.strftime("%Y-%m-%d %H:%M", time.localtime(recent)),
        "function",
    )


def test_counts_renamed_scripts_under_their_current_name(fish_home: Path) -> None:
    now = int(time.time())

    rows = run_usage(
        fish_home,
        [
            ("uv run transcribe_calls.py --dry-run", now - 2),
            ("/home/sanand/code/scripts/transcribe_calls.py --glob '*.opus'", now - 1),
            ("call --dry-run", now),
        ],
    )

    assert rows["call"] == (
        3,
        time.strftime("%Y-%m-%d %H:%M", time.localtime(now)),
        "script",
    )
    assert "transcribe_calls.py" not in rows
