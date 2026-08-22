#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# Source: https://chatgpt.com/c/6a6c4173-9404-83ec-9fea-af4478777bd0

"""Print Fish function and ~/code/scripts usage: fish_usage.py [DAYS] [--all]."""

import re
import shlex
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

args = [arg for arg in sys.argv[1:] if arg != "--all"]
if len(args) > 1 or (args and not args[0].isdigit()):
    raise SystemExit("Usage: fish_usage.py [DAYS] [--all]")
days, home = int(args[0]) if args else 90, Path.home()
history, scripts_dir = home / ".local/share/fish/fish_history", home / "code/scripts"
setup = scripts_dir / "setup.fish"
functions = set(re.findall(r"(?m)^function\s+([^\s(]+)", setup.read_text()))
scripts = {
    path.name
    for path in scripts_dir.iterdir()
    if path.is_file() and path.read_bytes().startswith(b"#!")
}
if "--all" in sys.argv[1:]:
    fish = "functions -n; for f in $fish_function_path/*.fish; test -f $f; and basename $f .fish; end"
    try:
        functions.update(
            subprocess.run(
                ["fish", "-ic", fish], capture_output=True, text=True, check=False
            ).stdout.split()
        )
    except FileNotFoundError:
        print("Warning: fish not found; using setup.fish only", file=sys.stderr)

prefixes = {"and", "or", "not", "time", "if", "while", "else"}
assignment = re.compile(r"^[A-Za-z_]\w*=")
wrappers = {
    "python",
    "python3",
    "bash",
    "sh",
    "zsh",
    "fish",
    "perl",
    "ruby",
    "node",
    "env",
    "sudo",
    "nohup",
    "xargs",
}


def command_groups(command: str) -> Iterator[list[str]]:
    """Yield Fish command words, excluding quoted separators and comments."""
    if command.lstrip().startswith("function "):
        return
    try:
        lexer = shlex.shlex(
            command.replace(r"\n", ";"), posix=True, punctuation_chars=";|&()"
        )
        lexer.whitespace_split, lexer.commenters = True, "#"
        words = []
        for token in lexer:
            if token and set(token) <= set(";|&()"):
                if words:
                    yield words
                    words = []
            else:
                words.append(token)
        if words:
            yield words
    except ValueError:
        if match := re.match(r"\s*([^\s;|&()<>]+)", command):
            yield [match.group(1)]


def script_name(token: str) -> str | None:
    """Return the ~/code/scripts script named by a command token."""
    if token in scripts:
        return token
    if token.startswith("./") and token[2:] in scripts:
        return token[2:]
    match = re.search(r"(?:^|/)code/scripts/([^/]+)$", token)
    return match.group(1) if match and match.group(1) in scripts else None


def invoked_names(words: list[str]) -> Iterator[str]:
    """Yield functions/scripts occupying executable positions in one Fish command."""
    i = 0
    while i < len(words) and (words[i] in prefixes or assignment.match(words[i])):
        i += 1
    while i < len(words) and words[i] in {"command", "builtin", "exec"}:
        i += 1
    if i >= len(words):
        return

    command = words[i]
    script = script_name(command)
    if command in functions:
        yield command
    if script:
        yield script

    base = Path(command).name
    if base == "git" and words[i + 1 : i + 2]:
        if git_script := script_name(f"git-{words[i + 1]}"):
            yield git_script
    elif (
        base in wrappers
        or script == "dev.sh"
        or (base == "uv" and words[i + 1 : i + 2] == ["run"])
    ):
        for token in words[i + 1 :]:
            if nested := script_name(token):
                yield nested
                break


uses, last, cutoff, command = Counter(), {}, time.time() - days * 86400, ""
for line in history.open(errors="replace"):
    if line.startswith("- cmd: "):
        command = line[7:].rstrip()
    elif line.startswith("  when: ") and (when := int(line[8:])) >= cutoff:
        for words in command_groups(command):
            for name in set(invoked_names(words)):
                uses[name] += 1
                last[name] = max(last.get(name, 0), when)
print("uses\tlast\tkind\tname")
for name in sorted(functions | scripts, key=lambda value: (-uses[value], value)):
    stamp = (
        f"{datetime.fromtimestamp(last[name], UTC).astimezone():%Y-%m-%d %H:%M}"
        if name in last
        else ""
    )
    print(
        uses[name], stamp, "function" if name in functions else "script", name, sep="\t"
    )
