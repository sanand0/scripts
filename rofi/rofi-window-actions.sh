#!/bin/bash
# Contextual action for native windows (Ctrl+Enter or Alt+Enter).
set -euo pipefail
id="${1:-}"
[[ "$id" =~ ^(0x[0-9a-fA-F]+|[0-9]+)$ ]] || exit 1

index="$(printf '%s\n' "Focus window" "Copy window title" "Copy window ID" "Close window" |
    rofi -dmenu -i -no-custom -format i -p 'Window')" || exit 0
case "$index" in
    0) xdotool windowactivate --sync "$id" ;;
    1) xdotool getwindowname "$id" | xclip -selection clipboard -in ;;
    2) printf '%s' "$id" | xclip -selection clipboard -in ;;
    3) xdotool windowclose "$id" ;;
esac
