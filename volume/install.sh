#!/usr/bin/env bash
set -euo pipefail

uuid=volume@sanand.net
source_dir=$(dirname -- "$0")
destination="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$uuid"
install -d "$destination"
install -m 644 "$source_dir/extension.js" "$source_dir/metadata.json" "$destination/"

if ! gnome-extensions enable "$uuid"; then
    printf 'Installed. After restarting GNOME Shell, run: gnome-extensions enable %s\n' "$uuid"
fi
