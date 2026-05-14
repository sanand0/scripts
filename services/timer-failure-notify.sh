#!/usr/bin/env bash

set -euo pipefail

UNIT="${1:?unit name required}"
OUTDIR="$HOME/.cache/sanand-scripts/timer-failures"
mkdir -p "$OUTDIR"

STAMP="$(date --iso-8601=seconds)"
SAFE_UNIT="${UNIT//[^A-Za-z0-9_.@-]/_}"
REPORT="$OUTDIR/$STAMP.$SAFE_UNIT.log"

{
  printf 'unit=%s\n' "$UNIT"
  printf 'time=%s\n' "$STAMP"
  printf '\n'
  systemctl --user status "$UNIT" --no-pager || true
  printf '\n--- recent journal ---\n'
  journalctl --user -u "$UNIT" -n 80 --no-pager || true
} > "$REPORT"

printf 'Recorded timer failure: %s\n' "$REPORT" >&2
