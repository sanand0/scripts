#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///

# Source: https://chatgpt.com/c/6a6c4173-9404-83ec-9fea-af4478777bd0

"""Print Fish function usage: fish_usage.py [DAYS] [--all]."""
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterator
import re, shlex, subprocess, sys, time

args = [arg for arg in sys.argv[1:] if arg != "--all"]
if len(args) > 1 or (args and not args[0].isdigit()):
    raise SystemExit("Usage: fish_usage.py [DAYS] [--all]")
days, home = int(args[0]) if args else 90, Path.home()
history, setup = home / ".local/share/fish/fish_history", home / "code/scripts/setup.fish"
functions = set(re.findall(r"(?m)^function\s+([^\s(]+)", setup.read_text()))
if "--all" in sys.argv[1:]:
    fish = "functions -n; for f in $fish_function_path/*.fish; test -f $f; and basename $f .fish; end"
    try:
        functions.update(subprocess.run(["fish", "-ic", fish], capture_output=True, text=True).stdout.split())
    except FileNotFoundError:
        print("Warning: fish not found; using setup.fish only", file=sys.stderr)

prefixes = {"and", "or", "not", "time", "if", "while", "else"}
assignment = re.compile(r"^[A-Za-z_]\w*=")
def command_names(command: str) -> Iterator[str]:
    """Yield tokens in Fish command position."""
    try:
        lexer = shlex.shlex(command.replace(r"\n", ";"), posix=True, punctuation_chars=";|&()")
        lexer.whitespace_split, lexer.commenters, start = True, "#", True
        for token in lexer:
            if token and set(token) <= set(";|&()"):
                start = True
            elif start and (token in prefixes or assignment.match(token)):
                continue
            elif start:
                if token not in {"command", "builtin", "exec"}:
                    yield token
                start = False
    except ValueError:
        if match := re.match(r"\s*([^\s;|&()<>]+)", command):
            yield match.group(1)

uses, last, cutoff, command = Counter(), {}, time.time() - days * 86400, ""
for line in history.open(errors="replace"):
    if line.startswith("- cmd: "):
        command = line[7:].rstrip()
    elif line.startswith("  when: ") and (when := int(line[8:])) >= cutoff:
        for function in command_names(command):
            if function in functions:
                uses[function] += 1
                last[function] = max(last.get(function, 0), when)
print("uses\tlast\tfunction")
for function in sorted(functions, key=lambda name: (-uses[name], name)):
    stamp = f"{datetime.fromtimestamp(last[function]):%Y-%m-%d %H:%M}" if function in last else ""
    print(uses[function], stamp, function, sep="\t")
