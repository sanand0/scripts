#!/bin/bash

set -euo pipefail

# rofi-fragments.sh: Pick a Markdown fragment by H2 title and paste its code fence.
#
# Expected Markdown shape (default file is fragments.md):
#   ## Fragment title
#   ```lang
#   ...snippet to paste...
#   ```
#
# Flow:
# 1) Parse all H2 headings and show them in rofi.
# 2) Read the selected heading.
# 3) Extract the first fenced code block under that heading.
# 4) Copy to clipboard and auto-paste when typing tools are available.
#
# Usage:
#   rofi-fragments.sh [path/to/fragments.md]
#
# Dependencies:
# - Required: awk, rofi
# - Optional Wayland: wl-copy (+ wtype for auto-type)
# - Optional X11: xclip (+ xdotool for Ctrl+V)

FILE="${1:-$HOME/code/blog/pages/prompts/fragments.md}"

if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

# Build the picker list from Markdown H2 headings.
# We intentionally key on H2 (##) to keep hierarchy simple and predictable.
mapfile -t HEADINGS < <(
  awk '
    /^##[[:space:]]+/ {
      h=$0
      sub(/^##[[:space:]]+/, "", h)
      print h
    }
  ' "$FILE"
)

[[ ${#HEADINGS[@]} -eq 0 ]] && { echo "No H2 headings found."; exit 1; }

# Show headings in rofi and capture the selected title.
# Empty selection means user cancelled; exit quietly.
CHOICE="$(printf '%s\n' "${HEADINGS[@]}" | rofi -dmenu -i -p 'Snippet')"
[[ -z "${CHOICE:-}" ]] && exit 0

# Extract the first fenced code block under the chosen heading.
#
# awk state machine:
# - in_target: currently inside the selected H2 section.
# - in_fence:  currently between opening and closing ``` fence lines.
# - done:      once the first block closes, stop scanning early.
#
# Fence language tags (```bash, ```python, ...) are supported because we match
# any line that starts with ``` as a fence delimiter.
CODE="$(
  awk -v target="$CHOICE" '
    BEGIN { in_target=0; in_fence=0; done=0 }

    /^##[[:space:]]+/ {
      if (done) exit
      h=$0
      sub(/^##[[:space:]]+/, "", h)
      in_target = (h == target)
      next
    }

    in_target && /^```/ {
      if (!in_fence) { in_fence=1; next }   # opening fence
      done=1; exit                           # closing fence
    }

    in_target && in_fence { print }
  ' "$FILE"
)"

[[ -z "${CODE:-}" ]] && { echo "No fenced code block found under: $CHOICE"; exit 1; }

# Copy and paste strategy:
# - Prefer Wayland tools first, then X11 tools.
# - If typing helpers are unavailable, still copy to clipboard.
# - If no clipboard tool exists, print to stdout as a safe fallback.
if command -v wl-copy >/dev/null 2>&1; then
  printf '%s' "$CODE" | wl-copy
  if command -v wtype >/dev/null 2>&1; then
    wtype "$CODE"
    exit 0
  fi
fi

if command -v xclip >/dev/null 2>&1; then
  printf '%s' "$CODE" | xclip -selection clipboard
  if command -v xdotool >/dev/null 2>&1; then
    xdotool key --clearmodifiers ctrl+v
    exit 0
  fi
fi

# Last resort for minimal environments (still useful in terminals/SSH).
printf '%s\n' "$CODE"
