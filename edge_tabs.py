#!/usr/bin/env -S uv run --script
"""Print Microsoft Edge tabs grouped by window from Chromium SNSS session files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import struct
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path


EDGE_CONFIG = Path.home() / ".config" / "microsoft-edge"


@dataclass
class Navigation:
    url: str
    title: str


@dataclass
class Tab:
    id: int
    window_id: int = 0
    visual_index: int = 0
    current_navigation_index: int = 0
    pinned: bool = False
    group: str | None = None
    group_id: tuple[int, int] | None = None
    navigations: dict[int, Navigation] = field(default_factory=dict)

    @property
    def current_navigation(self) -> Navigation | None:
        if self.current_navigation_index in self.navigations:
            return self.navigations[self.current_navigation_index]
        if not self.navigations:
            return None
        return self.navigations[sorted(self.navigations)[-1]]

    @property
    def url(self) -> str:
        navigation = self.current_navigation
        return navigation.url if navigation else ""

    @property
    def title(self) -> str:
        navigation = self.current_navigation
        return navigation.title if navigation else ""


@dataclass
class Window:
    id: int
    selected_tab_index: int = -1
    tabs: list[Tab] = field(default_factory=list)


class PickleReader:
    """Read the subset of Chromium Pickle fields used by session navigation commands."""

    def __init__(self, data: bytes, offset: int = 0):
        self.data = data
        self.offset = offset

    def int32(self) -> int:
        value = struct.unpack_from("<i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def uint64(self) -> int:
        value = struct.unpack_from("<Q", self.data, self.offset)[0]
        self.offset += 8
        return value

    def string(self) -> str:
        size = struct.unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        value = self.data[self.offset : self.offset + size].decode("utf-8", errors="replace")
        self.offset += size + (-size % 4)
        return value

    def string16(self) -> str:
        chars = struct.unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        size = chars * 2
        value = self.data[self.offset : self.offset + size].decode("utf-16-le", errors="replace")
        self.offset += size + (-size % 4)
        return value


def read_commands(data: bytes) -> Iterator[tuple[int, bytes]]:
    if len(data) < 8 or data[:4] != b"SNSS":
        raise ValueError("Not a Chromium SNSS session file")
    version = struct.unpack_from("<I", data, 4)[0]
    if version not in {1, 3}:
        raise ValueError(f"Unsupported SNSS version: {version}")

    offset = 8
    while offset + 3 <= len(data):
        size = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        if size == 0 or offset + size > len(data):
            break
        command_id = data[offset]
        payload_start = offset + 1
        yield command_id, data[payload_start : payload_start + size - 1]
        offset += size


def get_tab(tabs: dict[int, Tab], tab_id: int) -> Tab:
    return tabs.setdefault(tab_id, Tab(tab_id))


def get_window(windows: dict[int, Window], window_id: int) -> Window:
    return windows.setdefault(window_id, Window(window_id))


def parse_snss(data: bytes) -> list[Window]:
    """Return open browser windows and tabs from one Edge/Chromium SNSS file."""

    tabs: dict[int, Tab] = {}
    windows: dict[int, Window] = {}
    closed_tabs: set[int] = set()
    closed_windows: set[int] = set()
    group_titles: dict[tuple[int, int], str] = {}

    for command_id, payload in read_commands(data):
        if command_id == 0 and len(payload) >= 8:  # SetTabWindow
            window_id, tab_id = struct.unpack_from("<ii", payload)
            get_tab(tabs, tab_id).window_id = window_id
            get_window(windows, window_id)
        elif command_id == 2 and len(payload) >= 8:  # SetTabIndexInWindow
            tab_id, index = struct.unpack_from("<ii", payload)
            get_tab(tabs, tab_id).visual_index = index
        elif command_id == 5 and len(payload) >= 8:  # TabNavigationPathPrunedFromBack
            tab_id, index = struct.unpack_from("<ii", payload)
            tab = get_tab(tabs, tab_id)
            tab.navigations = {key: value for key, value in tab.navigations.items() if key < index}
        elif command_id == 6 and len(payload) >= 12:  # UpdateTabNavigation
            reader = PickleReader(payload, 4)  # First uint32 is Pickle payload size.
            tab_id = reader.int32()
            navigation_index = reader.int32()
            url = reader.string()
            title = reader.string16()
            get_tab(tabs, tab_id).navigations[navigation_index] = Navigation(url, title)
        elif command_id == 7 and len(payload) >= 8:  # SetSelectedNavigationIndex
            tab_id, index = struct.unpack_from("<ii", payload)
            get_tab(tabs, tab_id).current_navigation_index = index
        elif command_id == 8 and len(payload) >= 8:  # SetSelectedTabInIndex
            window_id, index = struct.unpack_from("<ii", payload)
            get_window(windows, window_id).selected_tab_index = index
        elif command_id == 11 and len(payload) >= 8:  # TabNavigationPathPrunedFromFront
            tab_id, index = struct.unpack_from("<ii", payload)
            tab = get_tab(tabs, tab_id)
            tab.current_navigation_index = max(-1, tab.current_navigation_index - index)
            tab.navigations = {
                key - index: value
                for key, value in tab.navigations.items()
                if key >= index
            }
        elif command_id == 12 and len(payload) >= 5:  # SetPinnedState
            tab_id, pinned = struct.unpack_from("<i?", payload)
            get_tab(tabs, tab_id).pinned = pinned
        elif command_id == 16 and len(payload) >= 4:  # TabClosed
            closed_tabs.add(struct.unpack_from("<i", payload)[0])
        elif command_id == 17 and len(payload) >= 4:  # WindowClosed
            closed_windows.add(struct.unpack_from("<i", payload)[0])
        elif command_id == 25 and len(payload) >= 25:  # SetTabGroup
            tab_id, high, low, has_group = struct.unpack_from("<i4xQQ?", payload)
            get_tab(tabs, tab_id).group_id = (high, low) if has_group else None
        elif command_id == 27 and len(payload) >= 24:  # SetTabGroupMetadata2
            reader = PickleReader(payload, 4)  # First uint32 is Pickle payload size.
            group_id = (reader.uint64(), reader.uint64())
            group_titles[group_id] = reader.string16()

    for tab in tabs.values():
        tab.group = group_titles.get(tab.group_id) if tab.group_id else None

    live_windows: dict[int, Window] = {}
    for tab in tabs.values():
        if tab.id in closed_tabs or tab.window_id in closed_windows or not tab.window_id or not tab.url:
            continue
        window = get_window(live_windows, tab.window_id)
        window.selected_tab_index = windows.get(tab.window_id, Window(tab.window_id)).selected_tab_index
        window.tabs.append(tab)

    result = [window for window in live_windows.values() if window.tabs]
    for window in result:
        window.tabs.sort(key=lambda tab: (tab.visual_index, tab.id))
    return result


def default_session_file(profile: Path = EDGE_CONFIG) -> Path:
    sessions_dir = profile / "Default" / "Sessions"
    candidates = sorted(sessions_dir.glob("Session_*"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No Session_* files found in {sessions_dir}")
    return candidates[-1]


def windows_to_json(windows: list[Window], source: Path) -> dict[str, object]:
    return {
        "timestamp": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "source": str(source),
        "window_count": len(windows),
        "tab_count": sum(len(window.tabs) for window in windows),
        "windows": [
            {
                "id": window.id,
                "selected_tab_index": window.selected_tab_index,
                "tab_count": len(window.tabs),
                "tabs": [
                    {
                        "id": tab.id,
                        "index": index,
                        "visual_index": tab.visual_index,
                        "active": index == window.selected_tab_index,
                        "group": tab.group,
                        "pinned": tab.pinned,
                        "title": tab.title,
                        "url": tab.url,
                    }
                    for index, tab in enumerate(window.tabs)
                ],
            }
            for window in windows
        ],
    }


def print_text(windows: list[Window], source: Path, urls_only: bool) -> None:
    print(f"# Timestamp: {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}")
    print(f"# Source: {source}")
    print(f"# Windows: {len(windows)}  Tabs: {sum(len(window.tabs) for window in windows)}")
    for window_index, window in enumerate(windows, 1):
        print()
        print(f"Window {window_index} (id {window.id}, {len(window.tabs)} tabs)")
        for tab_index, tab in enumerate(window.tabs, 1):
            active = " *" if tab_index - 1 == window.selected_tab_index else ""
            prefix = "[PIN] " if tab.pinned else ""
            suffix = f" [{tab.group}]" if tab.group else ""
            if urls_only or not tab.title:
                print(f"{tab_index:3d}.{active} {prefix}{tab.url}{suffix}")
            else:
                print(f"{tab_index:3d}.{active} {prefix}{tab.title}{suffix}\n     {tab.url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=EDGE_CONFIG, help="Edge profile root, default: %(default)s")
    parser.add_argument("--file", type=Path, help="Specific SNSS Session_* file to parse")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    parser.add_argument("--urls-only", action="store_true", help="Only print tab URLs in text output")
    args = parser.parse_args()

    source = args.file or default_session_file(args.profile)
    windows = parse_snss(source.read_bytes())
    if args.json:
        print(json.dumps(windows_to_json(windows, source), indent=2, ensure_ascii=False))
    else:
        print_text(windows, source, args.urls_only)


if __name__ == "__main__":
    main()
