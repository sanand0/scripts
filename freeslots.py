#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["dateparser>=1.2", "holidays>=0.73", "typer>=0.12"]
# ///
"""Suggest free meeting slots from Google Calendar via `gws`.

Examples:
  freeslots.py --timezone UK --days 7
  freeslots.py --timezone "San Francisco" --since tomorrow --until "next friday" | xclip -selection clipboard
  freeslots.py --timezone ET --duration 45 --format json | jaq .
  freeslots.py --describe | jaq .
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, available_timezones

import dateparser
import holidays
import typer

app = typer.Typer(add_completion=False, help=__doc__)

ALIASES = {
    "et": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "eastern": "America/New_York",
    "ct": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mt": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "sf": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "bay area": "America/Los_Angeles",
    "uk": "Europe/London",
    "london": "Europe/London",
    "bst": "Europe/London",
    "gmt": "Europe/London",
    "ist": "Asia/Kolkata",
    "india": "Asia/Kolkata",
    "india standard time": "Asia/Kolkata",
    "singapore": "Asia/Singapore",
    "sgt": "Asia/Singapore",
}
GWS_NOISE_PREFIXES = ("Using keyring backend:",)
FORMAT_CHOICES = {"text", "json"}
TIME_RE = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)?\s*$", re.I)
HOLIDAY_COUNTRIES = {
    "America/Los_Angeles": "US",
    "America/New_York": "US",
    "America/Chicago": "US",
    "America/Denver": "US",
    "Asia/Kolkata": "IN",
    "Asia/Singapore": "SG",
    "Europe/London": "GB",
}
ABBREV_OVERRIDES = {"Asia/Singapore": "SGT"}


def fail(message: str) -> None:
    raise typer.BadParameter(message)


def eprint(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def useful_stderr(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith(GWS_NOISE_PREFIXES))


def run_gws(args: list[str], *, config_dir: str = "") -> str:
    env = os.environ.copy()
    if config_dir:
        env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = config_dir
    result = subprocess.run(["gws", *args], env=env, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if stderr := useful_stderr(result.stderr):
        eprint(stderr)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, ["gws", *args], result.stdout, result.stderr)
    return result.stdout


def zone_key(zone: dt.tzinfo) -> str:
    return getattr(zone, "key", str(zone))


def local_zone() -> dt.tzinfo:
    local = dt.datetime.now().astimezone().tzinfo
    candidates = [os.environ.get("TZ"), Path("/etc/timezone").read_text().strip() if Path("/etc/timezone").exists() else ""]
    for name in candidates:
        if not name:
            continue
        try:
            zone = ZoneInfo(name)
        except Exception:
            continue
        if dt.datetime.now(zone).utcoffset() == dt.datetime.now(local).utcoffset():
            return zone
    return local


def resolve_zone(value: str | None) -> dt.tzinfo:
    if not value:
        return local_zone()
    raw = value.strip()
    key = re.sub(r"[_-]+", " ", raw).casefold()
    zone_name = ALIASES.get(key, raw)
    try:
        return ZoneInfo(zone_name)
    except Exception:
        matches = sorted(name for name in available_timezones() if key in name.replace("_", " ").casefold())
        if len(matches) == 1:
            return ZoneInfo(matches[0])
        hint = f" Did you mean {matches[0]}?" if matches else ""
        fail(f"unknown time zone: {value!r}.{hint}")


def abbrev(zone: dt.tzinfo, when: dt.datetime) -> str:
    return ABBREV_OVERRIDES.get(zone_key(zone), when.astimezone(zone).tzname() or zone_key(zone))


def zone_label(zone: dt.tzinfo, when: dt.datetime) -> str:
    return f"{abbrev(zone, when)} ({zone_key(zone)})"


def parse_date(value: str | None, zone: dt.tzinfo, *, default: dt.datetime) -> dt.datetime:
    if not value:
        return default
    settings = {
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": dt.datetime.now(zone).replace(tzinfo=None),
    }
    if isinstance(zone, ZoneInfo):
        settings["TIMEZONE"] = zone.key
    parsed = dateparser.parse(value, settings=settings)
    if parsed is None:
        fail(f"invalid date/time: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def parse_clock(value: str) -> dt.time:
    match = TIME_RE.match(value)
    if not match:
        fail(f"invalid time: {value!r}. Use 9am, 18:00, or 9:30 am.")
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = (match.group(3) or "").casefold()
    if minute > 59:
        fail(f"invalid minute in time: {value!r}")
    if suffix:
        if hour < 1 or hour > 12:
            fail(f"invalid 12-hour time: {value!r}")
        hour = 0 if hour == 12 and suffix == "am" else hour
        hour = hour + 12 if suffix == "pm" and hour < 12 else hour
    if hour > 23:
        fail(f"invalid hour in time: {value!r}")
    return dt.time(hour, minute)


def parse_hours(value: str) -> tuple[dt.time, dt.time]:
    parts = re.split(r"\s*(?:-|to|,)\s*", value.strip(), maxsplit=1, flags=re.I)
    if len(parts) != 2:
        fail(f"invalid hours: {value!r}. Use e.g. 9am-6pm.")
    start, end = parse_clock(parts[0]), parse_clock(parts[1])
    if start >= end:
        fail(f"start must be before end in hours: {value!r}")
    return start, end


def iso_utc(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_busy_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


def load_busy(start: dt.datetime, end: dt.datetime, calendar: str, *, config_dir: str, busy_json: Path | None) -> list[tuple[dt.datetime, dt.datetime]]:
    if busy_json:
        data = json.loads(busy_json.read_text())
    else:
        body = {"timeMin": iso_utc(start), "timeMax": iso_utc(end), "items": [{"id": calendar}]}
        data = json.loads(run_gws(["calendar", "freebusy", "query", "--json", compact_json(body), "--format", "json"], config_dir=config_dir))
    rows = ((data.get("calendars") or {}).get(calendar) or {}).get("busy") or []
    return sorted((parse_busy_time(row["start"]), parse_busy_time(row["end"])) for row in rows)


def dated_windows(start: dt.datetime, end: dt.datetime, zone: dt.tzinfo, hours: tuple[dt.time, dt.time]) -> list[tuple[dt.datetime, dt.datetime]]:
    local_start, local_end = start.astimezone(zone), end.astimezone(zone)
    day = local_start.date() - dt.timedelta(days=1)
    last_day = local_end.date() + dt.timedelta(days=1)
    windows = []
    while day <= last_day:
        begin = dt.datetime.combine(day, hours[0], zone)
        finish = dt.datetime.combine(day, hours[1], zone)
        if finish > start and begin < end:
            window_start = max(begin.astimezone(dt.UTC), start).astimezone(dt.UTC)
            window_end = min(finish.astimezone(dt.UTC), end).astimezone(dt.UTC)
            windows.append((window_start, window_end))
        day += dt.timedelta(days=1)
    return windows


def intersect(a: list[tuple[dt.datetime, dt.datetime]], b: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    out = []
    for left_start, left_end in a:
        for right_start, right_end in b:
            start, end = max(left_start, right_start), min(left_end, right_end)
            if start < end:
                out.append((start, end))
    return sorted(out)


def subtract(base: list[tuple[dt.datetime, dt.datetime]], blocks: list[tuple[dt.datetime, dt.datetime]]) -> list[tuple[dt.datetime, dt.datetime]]:
    free = []
    for start, end in base:
        pieces = [(start, end)]
        for busy_start, busy_end in blocks:
            next_pieces = []
            for piece_start, piece_end in pieces:
                if busy_end <= piece_start or busy_start >= piece_end:
                    next_pieces.append((piece_start, piece_end))
                    continue
                if piece_start < busy_start:
                    next_pieces.append((piece_start, busy_start))
                if busy_end < piece_end:
                    next_pieces.append((busy_end, piece_end))
            pieces = next_pieces
        free.extend(pieces)
    return sorted(free)


def long_enough(slots: list[tuple[dt.datetime, dt.datetime]], minutes: int) -> list[tuple[dt.datetime, dt.datetime]]:
    needed = dt.timedelta(minutes=minutes)
    return [(start, end) for start, end in slots if end - start >= needed]


def holiday_calendar(zone: dt.tzinfo, start: dt.datetime, end: dt.datetime) -> holidays.HolidayBase | None:
    country = HOLIDAY_COUNTRIES.get(zone_key(zone))
    if not country:
        return None
    years = range(start.astimezone(zone).year, end.astimezone(zone).year + 1)
    return holidays.country_holidays(country, years=years)


def filter_weekends(
    slots: list[tuple[dt.datetime, dt.datetime]],
    my_zone: dt.tzinfo,
    requested_zone: dt.tzinfo,
    *,
    include_weekends: bool,
) -> list[tuple[dt.datetime, dt.datetime]]:
    if include_weekends:
        return slots
    return [
        (start, end)
        for start, end in slots
        if start.astimezone(my_zone).date().weekday() < 5 and start.astimezone(requested_zone).date().weekday() < 5
    ]


def holiday_names(
    value: dt.datetime,
    my_zone: dt.tzinfo,
    requested_zone: dt.tzinfo,
    my_holidays: holidays.HolidayBase | None,
    requested_holidays: holidays.HolidayBase | None,
) -> list[str]:
    out = []
    for zone, calendar in [(my_zone, my_holidays), (requested_zone, requested_holidays)]:
        if calendar is None:
            continue
        day = value.astimezone(zone).date()
        if name := calendar.get(day):
            label = f"{name} ({abbrev(zone, value)})"
            if label not in out:
                out.append(label)
    return out


def split_holidays(
    slots: list[tuple[dt.datetime, dt.datetime]],
    my_zone: dt.tzinfo,
    requested_zone: dt.tzinfo,
    my_holidays: holidays.HolidayBase | None,
    requested_holidays: holidays.HolidayBase | None,
) -> tuple[list[tuple[dt.datetime, dt.datetime]], list[tuple[dt.datetime, dt.datetime]]]:
    regular, holiday = [], []
    for slot in slots:
        target = holiday if holiday_names(slot[0], my_zone, requested_zone, my_holidays, requested_holidays) else regular
        target.append(slot)
    return regular, holiday


def limit_per_day(slots: list[tuple[dt.datetime, dt.datetime]], requested_zone: dt.tzinfo, per_day: int) -> list[tuple[dt.datetime, dt.datetime]]:
    days: dict[dt.date, list[tuple[dt.datetime, dt.datetime]]] = {}
    for slot in slots:
        days.setdefault(slot[0].astimezone(requested_zone).date(), []).append(slot)
    picked = []
    for day_slots in days.values():
        picked.extend(sorted(day_slots, key=lambda item: (item[1] - item[0], -item[0].timestamp()), reverse=True)[:per_day])
    return sorted(picked)


def fmt_date(value: dt.datetime, zone: dt.tzinfo) -> str:
    return value.astimezone(zone).strftime("%a %-d %b %Y")


def fmt_short_date(value: dt.datetime, zone: dt.tzinfo) -> str:
    return value.astimezone(zone).strftime("%-d %b %Y")


def fmt_days(days: int) -> str:
    return f"{days} day" if days == 1 else f"{days} days"


def fmt_time(value: dt.datetime, zone: dt.tzinfo) -> str:
    return value.astimezone(zone).strftime("%-I:%M %p").lower()


def fmt_slot(row: dict[str, Any], requested_zone: dt.tzinfo, my_zone: dt.tzinfo) -> str:
    slot = (row["start_dt"], row["end_dt"])
    start, end = slot
    requested = f"{fmt_time(start, requested_zone)} - {fmt_time(end, requested_zone)} {abbrev(requested_zone, start)}"
    if zone_key(requested_zone) == zone_key(my_zone):
        text = f"{fmt_date(start, requested_zone)}: {requested}"
    else:
        mine = f"{fmt_time(start, my_zone)} - {fmt_time(end, my_zone)} {abbrev(my_zone, start)}"
        text = f"{fmt_date(start, requested_zone)}: {requested} ({mine})"
    if holiday := row.get("holiday"):
        text = f"{text} - holiday: {holiday}"
    return text


def render_text(result: dict[str, Any], requested_zone: dt.tzinfo, my_zone: dt.tzinfo) -> str:
    zones = (
        f"{abbrev(my_zone, result['start_dt'])} (mine and requested)"
        if zone_key(my_zone) == zone_key(requested_zone)
        else f"{abbrev(my_zone, result['start_dt'])} (mine) and {abbrev(requested_zone, result['start_dt'])} (requested)"
    )
    lines = [
        f"Time zones: {zones}",
        f"Dates: {result['dates']}",
        "",
        "Preferred slots:",
    ]
    preferred = result["preferred_slots"]
    lines.extend(fmt_slot(row, requested_zone, my_zone) for row in preferred)
    if not preferred:
        lines.append("None")
    lines.extend(["", "If none of the above are suitable:"])
    additional = result["additional_slots"]
    lines.extend(fmt_slot(row, requested_zone, my_zone) for row in additional)
    if not additional:
        lines.append("None")
    return "\n".join(lines)


def serialise_slots(
    slots: list[tuple[dt.datetime, dt.datetime]],
    requested_zone: dt.tzinfo,
    my_zone: dt.tzinfo,
    my_holidays: holidays.HolidayBase | None,
    requested_holidays: holidays.HolidayBase | None,
) -> list[dict[str, Any]]:
    rows = []
    for start, end in slots:
        row = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "requested": f"{fmt_date(start, requested_zone)} {fmt_time(start, requested_zone)}-{fmt_time(end, requested_zone)} {abbrev(requested_zone, start)}",
            "mine": f"{fmt_date(start, my_zone)} {fmt_time(start, my_zone)}-{fmt_time(end, my_zone)} {abbrev(my_zone, start)}",
            "start_dt": start,
            "end_dt": end,
        }
        if names := holiday_names(start, my_zone, requested_zone, my_holidays, requested_holidays):
            row["holiday"] = ", ".join(names)
        rows.append(row)
    return rows


def describe() -> dict[str, Any]:
    return {
        "name": "freeslots.py",
        "purpose": "Suggest preferred and fallback meeting slots from primary Google Calendar free/busy data.",
        "outputs": {"text": "human-friendly slots", "json": "structured slots with UTC ISO intervals"},
        "defaults": {
            "days": 7,
            "duration": 30,
            "my_preferred_hours": "9am-9pm",
            "my_extended_hours": "7am-11pm",
            "their_preferred_hours": "9am-6pm",
            "their_extended_hours": "8am-7pm",
            "slots_per_day": 3,
            "weekends": "excluded unless --include-weekends or a one-day explicit date is requested",
            "holidays": "shown in fallback slots with the holiday name",
        },
        "examples": [
            "freeslots.py --timezone UK --days 7",
            "freeslots.py --timezone 'San Francisco' --since tomorrow --until 'next friday'",
            "freeslots.py --timezone ET --duration 45 --format json | jaq .",
        ],
    }


@app.command()
def main(
    timezone: str | None = typer.Option(None, "--timezone", "--tz", help="Other person's time zone, e.g. ET, UK, San Francisco, Europe/London."),
    since: str | None = typer.Option(None, "--since", help="Start date/time. Defaults to now in my time zone."),
    until: str | None = typer.Option(None, "--until", help="End date/time. Defaults to --since + --days."),
    days: int = typer.Option(7, "--days", min=1, help="Date range length when --until is omitted."),
    work_hours: str = typer.Option("9am-6pm", "--work-hours", help="Other person's preferred hours."),
    extended_work_hours: str = typer.Option("8am-7pm", "--extended-work-hours", help="Other person's fallback hours."),
    my_hours: str = typer.Option("9am-9pm", "--my-hours", help="My preferred scheduling hours."),
    my_extended_hours: str = typer.Option("7am-11pm", "--my-extended-hours", help="My fallback scheduling hours."),
    duration: int = typer.Option(30, "--duration", min=1, help="Minimum meeting length in minutes."),
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum slots to print in each section."),
    slots_per_day: int = typer.Option(3, "--slots-per-day", min=1, help="Maximum slots per requested-time-zone day. Longest slots win."),
    include_weekends: bool = typer.Option(False, "--include-weekends", help="Include Saturdays and Sundays. One-day explicit searches include them automatically."),
    calendar: str = typer.Option("primary", "--calendar", help="Calendar ID for Google Calendar freebusy."),
    config_dir: str = typer.Option("", "--config-dir", help="Override GOOGLE_WORKSPACE_CLI_CONFIG_DIR for gws."),
    fmt: str = typer.Option("text", "--format", help="Output format: text|json."),
    busy_json: Path | None = typer.Option(None, "--busy-json", help="Read a saved freebusy JSON response instead of calling gws."),
    show_describe: bool = typer.Option(False, "--describe", help="Print machine-readable CLI metadata and exit."),
) -> None:
    if show_describe:
        print(compact_json(describe()))
        return
    if fmt not in FORMAT_CHOICES:
        fail(f"--format must be one of: {', '.join(sorted(FORMAT_CHOICES))}")

    my_zone = resolve_zone(None)
    requested_zone = resolve_zone(timezone) if timezone else my_zone
    now = dt.datetime.now(my_zone)
    until_given = until is not None
    start = parse_date(since, my_zone, default=now)
    end = parse_date(until, my_zone, default=start + dt.timedelta(days=days))
    if start >= end:
        fail("--since must be before --until")
    explicit_one_day = since is not None and end - start <= dt.timedelta(days=1)
    include_weekends = include_weekends or explicit_one_day

    preferred = intersect(
        dated_windows(start, end, my_zone, parse_hours(my_hours)),
        dated_windows(start, end, requested_zone, parse_hours(work_hours)),
    )
    extended = intersect(
        dated_windows(start, end, my_zone, parse_hours(my_extended_hours)),
        dated_windows(start, end, requested_zone, parse_hours(extended_work_hours)),
    )
    busy = load_busy(start, end, calendar, config_dir=config_dir, busy_json=busy_json)
    preferred_free = long_enough(subtract(preferred, busy), duration)
    extended_free = long_enough(subtract(extended, busy), duration)
    additional_free = long_enough(subtract(extended_free, preferred_free), duration)
    my_holidays = holiday_calendar(my_zone, start, end)
    requested_holidays = holiday_calendar(requested_zone, start, end)
    preferred_free = filter_weekends(preferred_free, my_zone, requested_zone, include_weekends=include_weekends)
    additional_free = filter_weekends(additional_free, my_zone, requested_zone, include_weekends=include_weekends)
    preferred_free, holiday_preferred = split_holidays(preferred_free, my_zone, requested_zone, my_holidays, requested_holidays)
    additional_free = additional_free + holiday_preferred
    preferred_free = limit_per_day(preferred_free, requested_zone, slots_per_day)
    additional_free = limit_per_day(
        additional_free,
        requested_zone,
        slots_per_day,
    )

    result = {
        "my_time_zone": zone_label(my_zone, start),
        "requested_time_zone": zone_label(requested_zone, start),
        "dates": f"{fmt_short_date(start, my_zone)} + {fmt_days(days)}" if not until_given else f"{fmt_short_date(start, my_zone)} to {fmt_short_date(end, my_zone)}",
        "start_dt": start,
        "end_dt": end,
        "include_weekends": include_weekends,
        "slots_per_day": slots_per_day,
        "preferred_slots": serialise_slots(preferred_free[:limit], requested_zone, my_zone, my_holidays, requested_holidays),
        "additional_slots": serialise_slots(additional_free[:limit], requested_zone, my_zone, my_holidays, requested_holidays),
    }
    if fmt == "json":
        result["start"] = result.pop("start_dt").isoformat()
        result["end"] = result.pop("end_dt").isoformat()
        for key in ["preferred_slots", "additional_slots"]:
            for row in result[key]:
                row.pop("start_dt")
                row.pop("end_dt")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_text(result, requested_zone, my_zone))


if __name__ == "__main__":
    app()
