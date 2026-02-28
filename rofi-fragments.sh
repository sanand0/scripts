#!/bin/bash

set -euo pipefail

FILE="${1:-$HOME/code/blog/pages/prompts/fragments.md}"

if [[ ! -f "$FILE" ]]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

# 1) List all H2 headings
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

# 2) Pick one heading in rofi
CHOICE="$(printf '%s\n' "${HEADINGS[@]}" | rofi -dmenu -i -p 'Snippet')"
[[ -z "${CHOICE:-}" ]] && exit 0

# 3) Extract first fenced code block under selected heading
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

# 4) Paste / copy (Wayland first, then X11)
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

# Fallback: print if auto-paste tools missing
printf '%s\n' "$CODE"
