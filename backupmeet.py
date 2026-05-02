#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///

"""Archive Google Meet recordings/transcripts from root.node@gmail.com Drive."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ACCOUNT = "root.node@gmail.com"
CONFIG_DIR = Path(os.environ.get("GWS_ROOT_CONFIG_DIR", "~/.config/gws-root.node@gmail.com")).expanduser()
DEST_DIR = Path("/home/sanand/Documents/Meet Recordings")
CALLS_DIR = Path("/home/sanand/Documents/calls")
GOOGLE_DOC = "application/vnd.google-apps.document"
GOOGLE_APPS = "application/vnd.google-apps."
FOLDER = "application/vnd.google-apps.folder"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MEET_NAMES = "(name contains 'Recording' or name contains 'Transcript' or name contains 'Notes by Gemini')"
FIELDS = "nextPageToken,files(id,name,mimeType,createdTime,modifiedTime,size,parents,webViewLink)"
FFMPEG = "ffmpeg -hide_banner -stats -v warning -i".split()
OPUS = "-c:a libopus -b:a 12k -ac 1 -application voip -vbr on -compression_level 10".split()


@dataclass
class DriveFile:
    id: str
    name: str
    mime: str
    created: str
    modified: str
    size: int | None = None
    parents: tuple[str, ...] = ()
    url: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> DriveFile:
        return cls(data["id"], data["name"], data["mimeType"], data["createdTime"], data["modifiedTime"], int(data["size"]) if data.get("size") else None, tuple(data.get("parents", [])), data.get("webViewLink", ""))

    @property
    def ext(self) -> str:
        suffix = self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""
        return {"video/mp4": "mp4", GOOGLE_DOC: "docx", DOCX: "docx", "text/plain": "txt"}.get(
            self.mime, suffix or "bin"
        )

    @property
    def modified_ts(self) -> float:
        return datetime.fromisoformat(self.modified.replace("Z", "+00:00")).timestamp()

    @property
    def date(self) -> str:
        if match := re.search(r"20\d{2}\D+[01]?\d\D+[0-3]?\d", self.name):
            y, m, d = re.split(r"\D+", match.group(0))[:3]
            return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        return self.created.split("T", 1)[0]

    @property
    def title(self) -> str:
        stem = self.name.rsplit(".", 1)[0] if "." in self.name else self.name
        title = re.sub(r"[\s\W]*20\d{2}\W+\d{1,2}\W+\d{1,2}.*$", "", stem)
        title = re.sub(r"[\s-]*(Recording|Transcript|Notes by Gemini)$", "", title, flags=re.I)
        return clean(title or stem)

    def matches_type(self, kind: str | None) -> bool:
        if not kind:
            return True
        key = kind.lower()
        checks = {
            "video": self.mime == "video/mp4" or self.ext == "mp4",
            "mp4": self.mime == "video/mp4" or self.ext == "mp4",
            "transcript": "transcript" in self.name.lower() or self.mime == GOOGLE_DOC or self.ext == "docx",
            "notes": "notes by gemini" in self.name.lower(),
            "doc": self.ext == "docx" or self.mime == GOOGLE_DOC,
            "docx": self.ext == "docx" or self.mime == GOOGLE_DOC,
        }
        if key in checks:
            return checks[key]
        if key.startswith("ext:"):
            return self.ext == key.removeprefix("ext:")
        if kind.startswith("mime:"):
            return self.mime == kind.removeprefix("mime:")
        fail(f"unknown --type '{kind}'")


@dataclass
class Archive:
    file: DriveFile
    output: Path
    opus: Path | None

    @classmethod
    def for_file(cls, file: DriveFile, dest: Path, calls: Path) -> Archive:
        output = dest / f"{file.date} {file.title}.{file.ext}"
        opus = calls / f"{output.stem}.opus" if file.ext == "mp4" else None
        return cls(file, output, opus)

    def event(self, status: str, event: str) -> dict[str, Any]:
        return {
            "event": event,
            "status": status,
            "id": self.file.id,
            "source_name": self.file.name,
            "output": str(self.output),
            "opus": str(self.opus or ""),
        }

    def complete(self) -> bool:
        if not self.output.exists() or self.output.stat().st_size == 0:
            return False
        if self.file.mime == GOOGLE_DOC:
            with self.output.open("rb") as handle:
                if handle.read(2) != b"PK":
                    return False
        elif self.file.size is not None and self.output.stat().st_size != self.file.size:
            return False
        return self.output.stat().st_mtime >= self.file.modified_ts

    def done(self) -> bool:
        return self.complete() and (not self.opus or self.opus.exists() and self.opus.stat().st_size > 0)


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in {"account": ACCOUNT, "config-dir": CONFIG_DIR, "dest": DEST_DIR, "calls-dir": CALLS_DIR, "older-than": "7d"}.items():
        parser.add_argument(f"--{name}", default=default, type=Path if isinstance(default, Path) else str)
    for name in ["after", "before", "name", "type"]:
        parser.add_argument(f"--{name}")
    parser.add_argument("--limit", type=int)
    for name in ["dry-run", "yes"]:
        parser.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default=None)
    return parser.parse_args()


def fail(message: str) -> None:
    raise SystemExit(f"backupmeet.py: {message}")


def json_compact(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"))


def clean(text: str) -> str:
    text = re.sub(r"[/\r\n\t]", " ", text)
    text = re.sub(r"[\x00-\x1f]", "", text)
    return re.sub(r"\s+", " ", text).strip(" .")


def day_start(spec: str) -> str:
    if match := re.fullmatch(r"(\d+)d", spec):
        day = datetime.now(UTC) - timedelta(days=int(match.group(1)))
    elif match := re.fullmatch(r"(\d+)\s+months?\s+ago", spec, re.I):
        day = datetime.now(UTC) - timedelta(days=30 * int(match.group(1)))
    else:
        day = datetime.fromisoformat(spec).replace(tzinfo=UTC)
    return f"{day.date().isoformat()}T00:00:00Z"


def run_gws(args: list[str], config_dir: Path, output: Path | None = None) -> str:
    env = os.environ.copy()
    env.pop("GOOGLE_WORKSPACE_CLI_TOKEN", None)
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = str(config_dir)
    cwd = None
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        args = [*args, "--output", output.name]
        cwd = output.parent
    return subprocess.run(["gws", *args], check=True, cwd=cwd, env=env, stdout=subprocess.PIPE, text=True).stdout


def gws_json(args: list[str], config_dir: Path) -> Any:
    return json.loads(run_gws(args, config_dir))


def verify_account(config_dir: Path, account: str) -> str:
    if not config_dir.exists():
        fail(
            f"gws config dir not found for {account}: {config_dir}. "
            f'Run: GOOGLE_WORKSPACE_CLI_CONFIG_DIR="{config_dir}" gws auth login'
        )
    actual = gws_json(["drive", "about", "get", "--params", '{"fields":"user(emailAddress)"}'], config_dir)["user"][
        "emailAddress"
    ]
    if actual != account:
        fail(f"refusing to continue: {config_dir} is authenticated as {actual}, expected {account}")
    return actual


def query_for(before: str, after: str) -> str:
    query = f"trashed=false and mimeType != '{FOLDER}' and {MEET_NAMES} and createdTime < '{before}'"
    return f"{query} and createdTime >= '{after}'" if after else query


def discover(config_dir: Path, before: str, after: str) -> list[DriveFile]:
    params = {"q": query_for(before, after), "fields": FIELDS, "orderBy": "createdTime", "pageSize": 100}
    out = run_gws(["drive", "files", "list", "--params", json_compact(params), "--page-all", "--page-limit", "100"], config_dir)
    return [DriveFile.from_json(item) for line in out.splitlines() for item in json.loads(line).get("files", [])]


def eligible(file: DriveFile) -> bool:
    return file.mime == GOOGLE_DOC or not file.mime.startswith(GOOGLE_APPS)


def download(archive: Archive, config_dir: Path) -> None:
    file = archive.file
    tmp = archive.output.with_name(f".backupmeet.{os.getpid()}.{archive.output.name}")
    if file.mime == GOOGLE_DOC:
        args = ["drive", "files", "export", "--params", json_compact({"fileId": file.id, "mimeType": DOCX})]
    elif file.mime.startswith(GOOGLE_APPS):
        fail(f"cannot archive unsupported Google Drive item: {file.name} ({file.mime})")
    else:
        args = ["drive", "files", "get", "--params", json_compact({"fileId": file.id, "alt": "media"})]
    run_gws(args, config_dir, tmp)
    os.utime(tmp, (file.modified_ts, file.modified_ts))
    tmp.replace(archive.output)


def convert(archive: Archive) -> None:
    if not archive.opus or archive.opus.exists() and archive.opus.stat().st_size > 0:
        return
    archive.opus.parent.mkdir(parents=True, exist_ok=True)
    tmp = archive.opus.with_name(f".backupmeet.{os.getpid()}.{archive.opus.name}")
    subprocess.run([*FFMPEG, str(archive.output), *OPUS, str(tmp)], check=True)
    tmp.replace(archive.opus)


def drive_path(file: DriveFile, config_dir: Path, cache: dict[str, dict[str, Any]]) -> str:
    parts = [file.name]
    parent_id = file.parents[0] if file.parents else None
    while parent_id:
        cache[parent_id] = cache.get(parent_id) or gws_json(
            ["drive", "files", "get", "--params", json_compact({"fileId": parent_id, "fields": "id,name,parents"})],
            config_dir,
        )
        parent = cache[parent_id]
        parts.append(parent["name"])
        parent_id = (parent.get("parents") or [None])[0]
    return "/".join(reversed(parts))


def delete_or_warn(archive: Archive, config_dir: Path, parent_cache: dict[str, dict[str, Any]]) -> str:
    try:
        run_gws(["drive", "files", "delete", "--params", json_compact({"fileId": archive.file.id})], config_dir)
        return "archived"
    except subprocess.CalledProcessError:
        try:
            location = drive_path(archive.file, config_dir, parent_cache)
        except subprocess.CalledProcessError:
            location = archive.file.name
        link = f" ({archive.file.url})" if archive.file.url else ""
        print(f"delete failed: manually delete Drive file: {location}{link}", file=sys.stderr)
        return "archived-delete-failed"


def emit(format_: str, event: dict[str, Any]) -> None:
    if format_ == "json":
        print(json_compact(event))
    elif event["event"] == "summary":
        print(f"summary: matched={event['matched']} processed={event['processed']} dry_run={int(event['dry_run'])}")
    else:
        opus = f"; opus: {event['opus']}" if event.get("opus") else ""
        print(f"{event['status']}: {event['source_name']} -> {event['output']}{opus}")


def main() -> None:
    args = cli()
    format_ = args.format or ("text" if sys.stdout.isatty() else "json")
    for tool in ["gws", *([] if args.dry_run else ["ffmpeg"])]:
        if not shutil.which(tool):
            fail(f"missing dependency: {tool}")

    actual = verify_account(args.config_dir, args.account)
    before = day_start(args.before or args.older_than)
    after = day_start(args.after) if args.after else ""
    if format_ == "text":
        print(f"account: {actual}\nquery: {query_for(before, after)}")

    matched = [
        file
        for file in discover(args.config_dir, before, after)
        if eligible(file) and (not args.name or args.name.lower() in file.name.lower()) and file.matches_type(args.type)
    ]
    archives = [Archive.for_file(file, args.dest, args.calls_dir) for file in matched[: args.limit]]
    if archives and not args.dry_run and not args.yes:
        if not sys.stdin.isatty():
            fail("refusing to delete Drive files without --yes in non-interactive mode")
        if input(f"Archive and permanently delete {len(archives)} Drive files from {args.account}? Type yes: ") != "yes":
            fail("aborted")

    parent_cache: dict[str, dict[str, Any]] = {}
    for archive in archives:
        if archive.done():
            emit(format_, archive.event("skipped-existing", "skipped"))
            continue
        if args.dry_run:
            emit(format_, archive.event("dry-run", "planned"))
            continue
        download(archive, args.config_dir)
        convert(archive)
        emit(format_, archive.event(delete_or_warn(archive, args.config_dir, parent_cache), "archived"))

    emit(format_, {"event": "summary", "matched": len(matched), "processed": len(archives), "dry_run": args.dry_run, "account": actual, "before": before, "after": after})


if __name__ == "__main__":
    main()
