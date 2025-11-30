#!/bin/bash

set -euo pipefail

FRECENT="$HOME/.cache/sanand-scripts/frecent.txt"
ICON_FILE="/usr/share/icons/Adwaita/16x16/mimetypes/text-x-generic.png"

# Initial selection => list all files.
if [[ "${ROFI_RETV:-0}" == "0" ]]; then
    # Enable hotkeys (Ctrl+Enter, etc.)
    echo -en "\0use-hot-keys\x1ftrue\n"

    # Show most frequent-recent ($FRECENT) files
    tail -n 1000 "$FRECENT" \
        | sort \
        | uniq -c \
        | sort -rn \
        | awk '{$1=""; sub(/^ /, ""); print}'

    # Show all other files. Ensure files._* appear before other files
    cat $(printf "%s\n" $HOME/.cache/sanand-scripts/files*.txt | sort -r)

    exit 0
fi

# When an item is selected, rofi calls us again with the selected row as $ROFI_INFO or $*.
payload="${ROFI_INFO:-$*}"

# Prepend payload to $FRECENT
{ echo "$payload"; cat "$FRECENT"; } > "${FRECENT}.tmp"
mv "${FRECENT}.tmp" "$FRECENT"

case "$payload" in
  # If it begins with /, it's an absolute path.
  /*)    fullpath="$payload" ;;
  # If it begins with ~/, expand to $HOME.
  "~/"*) fullpath="$HOME/${payload#~/}" ;;
  # Otherwise, prepend $HOME/.
  *)     fullpath="$HOME/$payload" ;;
esac

case "${ROFI_RETV}" in
  # Return: Open the file
  1) setsid open "$fullpath" >/dev/null 2>&1 & ;;
  # Shift+Return copies the file path to clipboard
  10) setsid --fork sh -c 'printf %s "$1" | xclip -selection clipboard -in' _ "$fullpath" >/dev/null 2>&1 ;;
  # Ctrl+Return: Open the file location in Nautilus
  11) setsid nautilus --select -- "$fullpath" >/dev/null 2>&1 & ;;
  # Ctrl+Shift+Return: Open the directory in VS Code
  12) setsid code --folder-uri "file://$(dirname "$fullpath")" >/dev/null 2>&1 & ;;
esac
