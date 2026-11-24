"""Disposable file metadata for incremental conversation backups."""

import json
import os
from pathlib import Path
import time


def file_stamp(path: Path | os.DirEntry) -> list[int] | None:
    """Detect edits, atomic replacements, and timestamp-preserving copies."""
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns]


def cached_file(path: Path | os.DirEntry, previous: dict, current: dict, read):
    stamp = file_stamp(path)
    entry = previous.get(path.name)
    if entry is None or entry[0] != stamp:
        entry = [stamp, read(Path(path) if isinstance(path, os.DirEntry) else path)]
    current[path.name] = entry
    return entry[1]


def cache_version(*sources: Path) -> list:
    """Invalidate on code or local timezone changes that can affect results."""
    return [os.environ.get("TZ"), list(time.tzname),
            *map(file_stamp, (Path("/etc/localtime"), Path(__file__), *sources))]


def load_cache(path: Path | None, version: list) -> dict:
    if path is None:
        return {}
    try:
        cache = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return {}
    return cache if isinstance(cache, dict) and cache.get("version") == version else {}
