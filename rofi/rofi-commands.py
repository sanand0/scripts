#!/usr/bin/python3
"""Dynamic GNOME panel actions and configurable CLI commands for Rofi.

Add entries to rofi-commands.tsv as: Label<TAB>terminal|background<TAB>working_dir<TAB>command.
Panel controls are rediscovered through AT-SPI before every click; nothing is
hardcoded to an icon position. Requires GNOME Shell on X11 for panel clicks.
"""
from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REGISTRY = HERE / "rofi-commands.tsv"


@dataclass
class Item:
    name: str
    kind: str
    x: int = 0
    y: int = 0
    mode: str = ""
    cwd: str = ""
    command: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"


def panel_items() -> list[Item]:
    if os.environ.get("ROFI_COMMANDS_NO_PANEL"):
        return []
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi

        desktop = Atspi.get_desktop(0)
        shell = next((desktop.get_child_at_index(i)
                      for i in range(desktop.get_child_count())
                      if desktop.get_child_at_index(i).get_name() == "gnome-shell"), None)
        if shell is None:
            return []
        window = shell.get_child_at_index(0)
        root = window.get_child_at_index(0)
        screen = root.get_extents(Atspi.CoordType.SCREEN)

        def children(node):
            for index in range(node.get_child_count()):
                yield node.get_child_at_index(index)

        def box(node):
            r = node.get_extents(Atspi.CoordType.SCREEN)
            return r.x, r.y, r.width, r.height

        def visible(node):
            x, y, w, h = box(node)
            return (8 <= w <= screen.width and 8 <= h <= screen.height
                    and x >= screen.x and y >= screen.y
                    and x + w <= screen.x + screen.width
                    and y + h <= screen.y + screen.height)

        # Find the panel by its geometry, not its index in GNOME's accessible tree.
        candidates = []
        for node in children(root):
            x, y, w, h = box(node)
            if w >= screen.width * 0.7 and 20 <= h <= 80 and (
                    y <= screen.y + 80 or y + h >= screen.y + screen.height - 80):
                candidates.append(node)
        if not candidates:
            return []
        panel = candidates[0]
        while panel.get_child_count() == 1:
            child = panel.get_child_at_index(0)
            if box(child) != box(panel):
                break
            panel = child

        entries = []

        def names(node, depth=0):
            if depth > 9 or not visible(node):
                return []
            role = node.get_role_name()
            name = node.get_name()
            if name and role in ("menu", "toggle button", "push button"):
                x, y, w, h = box(node)
                return [Item("Activities / Workspaces" if name == "Activities" else name,
                             "panel", x + w // 2, y + h // 2)]
            found = []
            for child in children(node):
                found.extend(names(child, depth + 1))
            return found

        def labels(node, depth=0):
            if depth > 8 or not visible(node):
                return []
            result = [node.get_name()] if node.get_role_name() == "label" and node.get_name() else []
            for child in children(node):
                result.extend(labels(child, depth + 1))
            return result

        for section in children(panel):
            if not visible(section):
                continue
            # The AppIndicator container groups unrelated controls; handle each
            # child separately so anonymous indicators such as Vitals survive.
            parts = (list(children(section)) if section.get_child_count() >= 8
                     else [section])
            for part in parts:
                if not visible(part):
                    continue
                section_items = names(part)
                if section_items:
                    entries.extend(section_items)
                    continue
                text = " ".join(labels(part))
                x, y, w, h = box(part)
                if re.search(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", text):
                    entries.append(Item("Date and Time", "panel", x + w // 2, y + h // 2))
                elif sum(bool(re.search(r"\d", v)) for v in labels(part)) >= 3:
                    entries.append(Item("Vitals", "panel", x + w // 2, y + h // 2))
                elif x + w >= screen.x + screen.width - 1 and 0 < w <= 20:
                    entries.append(Item("Show Desktop", "panel", x + w // 2, y + h // 2))

        counts = {}
        for item in entries:
            counts[item.name] = counts.get(item.name, 0) + 1
            if counts[item.name] > 1:
                item.name += f" ({counts[item.name]})"
        return sorted(entries, key=lambda item: -item.x)
    except Exception as error:
        print(f"GNOME panel unavailable: {error}", file=sys.stderr)
        return []


def configured_items() -> list[Item]:
    if not REGISTRY.is_file():
        return []
    entries = []
    for number, line in enumerate(REGISTRY.read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t", 3)
        if len(fields) != 4 or fields[1] not in ("terminal", "background"):
            print(f"Invalid command in {REGISTRY}:{number}", file=sys.stderr)
            continue
        name, mode, cwd, command = fields
        if name and command:
            entries.append(Item(name, "command", mode=mode, cwd=cwd, command=command))
    return entries


def find_item(key: str) -> Item:
    source = configured_items() if key.startswith("command:") else panel_items()
    match = next((item for item in source if item.key == key), None)
    if match is None:
        raise ValueError(f"Item is no longer available: {key}")
    return match


def shell_command(item: Item, mode: str) -> None:
    cwd = str(Path(item.cwd).expanduser())
    if not Path(cwd).is_dir():
        raise ValueError(f"Directory not found: {cwd}")
    if mode == "terminal":
        subprocess.Popen([str(HERE / "rofi-files.sh"), "--terminal", cwd, item.command],
                         start_new_session=True, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    else:
        cache = Path.home() / ".cache/sanand-scripts"
        cache.mkdir(parents=True, exist_ok=True)
        with (cache / "rofi-commands.log").open("a") as log:
            log.write(f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] "
                      f"{item.name}: {item.command}\n")
            log.flush()
            subprocess.Popen(["bash", "-lc",
                              f"cd -- {shlex.quote(cwd)} && {item.command}"],
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT)


def activate(item: Item, action: str = "run") -> None:
    if action == "copy":
        content = item.command if item.kind == "command" else item.name
        subprocess.run(["xclip", "-selection", "clipboard", "-in"],
                       input=content, text=True, check=True)
    elif item.kind == "panel":
        if action not in ("run", "right"):
            raise ValueError(f"Unknown panel action: {action}")
        subprocess.run(["xdotool", "mousemove", "--sync", str(item.x), str(item.y),
                        "click", "3" if action == "right" else "1"], check=True)
    elif action == "edit":
        subprocess.Popen(["code", "--reuse-window", str(REGISTRY)], start_new_session=True)
    else:
        shell_command(item, "terminal" if action == "terminal" else item.mode)


def action_menu(key: str) -> None:
    item = find_item(key)
    options = ([("Click", "run"), ("Right-click", "right"), ("Copy name", "copy")]
               if item.kind == "panel" else
               [("Run", "run"), ("Run in VS Code terminal", "terminal"),
                ("Copy command", "copy"), ("Edit command registry", "edit")])
    chosen = subprocess.run(["rofi", "-dmenu", "-no-custom", "-format", "i",
                             "-p", item.name], input="\n".join(label for label, _ in options),
                            text=True, capture_output=True).stdout.strip()
    if chosen.isdigit() and int(chosen) < len(options):
        activate(item, options[int(chosen)][1])


def detach(*args: str) -> None:
    subprocess.Popen([sys.executable, __file__, *args], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)


def close_picker() -> None:
    file = os.environ.get("ROFI_PICKER_PIDFILE", "")
    if file and Path(file).is_file():
        value = Path(file).read_text().strip()
        if value.isdigit():
            try:
                os.kill(int(value), signal.SIGTERM)
            except ProcessLookupError:
                pass


def main() -> None:
    if len(sys.argv) > 2 and sys.argv[1] == "--activate":
        activate(find_item(sys.argv[2]))
    elif len(sys.argv) > 2 and sys.argv[1] == "--menu":
        action_menu(sys.argv[2])
    elif sys.argv[1:] == ["--dump"]:
        for item in panel_items() + configured_items():
            print(f"{item.kind}\t{item.name}\t{item.x},{item.y}\t{item.mode}\t{item.command}")
    elif os.environ.get("ROFI_RETV", "0") == "0":
        sys.stdout.buffer.write(b"\0use-hot-keys\x1ftrue\n\0no-custom\x1ftrue\n")
        for item in panel_items() + configured_items():
            label = f"{'Panel' if item.kind == 'panel' else 'Command'}: {item.name}"
            sys.stdout.buffer.write(f"{label}\0info\x1f{item.key}\n".encode())
    else:
        key = os.environ.get("ROFI_INFO", "")
        if key:
            detach("--menu" if int(os.environ["ROFI_RETV"]) >= 10 else "--activate", key)
            close_picker()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"rofi-commands: {exc}", file=sys.stderr)
        subprocess.run(["notify-send", "Rofi commands", str(exc)], check=False)
        sys.exit(1)
