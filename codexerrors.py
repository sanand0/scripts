#!/usr/bin/env -S uv run --script
"""Summarize failing shell commands in Codex JSONL logs."""
import argparse
import json
import re
import shlex
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def parse_ts(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def extract_command(args_raw: str) -> tuple[str | None, str | None]:
    """Return (base command, full command) from the serialized arguments field."""
    if not isinstance(args_raw, str):
        return None, None
    try:
        parsed = json.loads(args_raw)
    except json.JSONDecodeError:
        parsed = args_raw

    cmd_field = None
    if isinstance(parsed, dict):
        cmd_field = parsed.get("command")
    elif isinstance(parsed, str):
        cmd_field = parsed

    if isinstance(cmd_field, list) and cmd_field:
        full = " ".join(map(str, cmd_field))
        return str(cmd_field[0]), full
    if isinstance(cmd_field, str):
        full = cmd_field.strip()
        try:
            base = shlex.split(full)[0]
        except Exception:
            base = full.split()[0] if full.split() else full
        return base, full
    return None, None


def shorten(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    head = limit // 2
    tail = limit - head - 3
    return f"{text[:head]}...{text[-tail:]}"


def clean(text: str) -> str:
    return " ".join(text.split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Emit TSV of failing/missing commands from JSONL logs.")
    parser.add_argument("--log-dir", default=".", help="Directory to scan recursively for *.jsonl logs.")
    parser.add_argument("--start", help="ISO datetime (inclusive).")
    parser.add_argument("--end", help="ISO datetime (inclusive).")
    parser.add_argument("--max-detail", type=int, default=160, help="Max chars to show for command detail.")
    args = parser.parse_args()

    start_ts = parse_ts(args.start) if args.start else None
    end_ts = parse_ts(args.end) if args.end else None

    call_meta: dict[str, tuple[str, str]] = {}
    counts: Counter[tuple[str, str, str, str]] = Counter()
    exit_re = re.compile(r"Exit code:\s*(-?\d+)")

    def within_range(ts: datetime) -> bool:
        if start_ts and ts < start_ts:
            return False
        if end_ts and ts > end_ts:
            return False
        return True

    def rows_for_file(path: Path) -> Iterable[tuple[str, str, str]]:
        try:
            fh = path.open()
        except OSError:
            return []
        with fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts_raw = rec.get("timestamp")
                if not ts_raw:
                    continue
                ts = parse_ts(ts_raw)
                if not within_range(ts):
                    continue

                payload = rec.get("payload", {})
                ptype = payload.get("type")
                if ptype == "function_call" and payload.get("name") in {"shell_command", "shell"}:
                    base_cmd, full_cmd = extract_command(payload.get("arguments", ""))
                    if base_cmd:
                        call_meta[payload.get("call_id")] = (base_cmd, full_cmd or base_cmd)
                    continue

                if ptype != "function_call_output":
                    continue
                call_id = payload.get("call_id")
                meta = call_meta.get(call_id)
                if not meta:
                    continue
                base_cmd, full_cmd = meta
                output = payload.get("output", "") or ""
                exit_code = None

                try:
                    output_json = json.loads(output)
                    if isinstance(output_json, dict):
                        meta_code = output_json.get("metadata", {}).get("exit_code")
                        if meta_code is not None:
                            exit_code = str(meta_code)
                        inner_out = output_json.get("output")
                        if isinstance(inner_out, str):
                            output = inner_out
                except json.JSONDecodeError:
                    pass

                match = exit_re.search(output)
                if match:
                    exit_code = match.group(1)

                lower_out = output.lower()

                is_missing = exit_code == "127" or (exit_code is None and "command not found" in lower_out)
                if is_missing:
                    yield (base_cmd, full_cmd, "missing", exit_code or "127")
                    continue

                if "execution error" in lower_out and exit_code != "0":
                    yield (base_cmd, full_cmd, "failure", "execution-error")
                    continue

                if exit_code and exit_code != "0":
                    yield (base_cmd, full_cmd, "failure", exit_code)

    for path in sorted(Path(args.log_dir).rglob("*.jsonl")):
        for row in rows_for_file(path):
            counts[row] += 1

    kind_rank = {"missing": 0, "failure": 1}
    print("command\tdetail\tkind\texit_code\tcount")
    for (cmd, detail, kind, code), count in sorted(
        counts.items(),
        key=lambda x: (kind_rank.get(x[0][2], 9), x[1], x[0][0], x[0][3], x[0][1]),
    ):
        detail_out = shorten(clean(detail), args.max_detail)
        print(f"{cmd}\t{detail_out}\t{kind}\t{code}\t{count}")


if __name__ == "__main__":
    import os
    os.chdir("/home/sanand/.codex/sessions/")

    main()
