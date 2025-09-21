#!/usr/bin/env bash
# Set up systemd services if required and report status

set -euo pipefail
# Expand only if files exist
shopt -s nullglob

DEST="$HOME/.config/systemd/user"
mkdir -p "$DEST"

# Link .service/.timer files only if needed
for f in *.service *.timer; do
  base="${f##*/}"; target="$DEST/$base"; src="$PWD/$f"
  if [[ -L "$target" ]]; then
    [[ "$(readlink -f "$target")" == "$src" ]] || { rm -f "$target"; systemctl --user link "$src" >/dev/null; }
  elif [[ ! -e "$target" ]]; then
    systemctl --user link "$src" >/dev/null
  fi
done

# Reload user manager to pick up changes
systemctl --user daemon-reload

# Enable & start timers (safe to re-run)
for t in *.timer; do
  [[ -e "$t" ]] || continue
  systemctl --user enable --now "${t##*/}" >/dev/null || true
done

# Print status
for t in *.timer *.service; do
  echo $t
  [[ -e "$t" ]] || { echo "  (none)"; break; }
  systemctl --user show "${t##*/}" | grep -E '^(UnitFileState|NextElapseUSecRealtime)' | sed 's/^/    /'
done
