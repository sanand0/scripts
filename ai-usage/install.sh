#!/usr/bin/env bash
# Install/update the GNOME Shell indicator (run from ~/code/scripts/ai-usage).
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
SCRIPTS="$HOME/code/scripts"
EXPECTED="$SCRIPTS/ai-usage"
[[ "$ROOT" == "$EXPECTED" ]] || { echo "Place this folder at $EXPECTED first" >&2; exit 1; }
UUID=ai-usage@sanand.net
DEST="$HOME/.local/share/gnome-shell/extensions/$UUID"
for tool in jq curl flock glib-compile-schemas gnome-extensions; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
[[ -x "$SCRIPTS/ccusage" && -x "$SCRIPTS/codexusage" ]] || { echo 'Usage scripts must be executable' >&2; exit 1; }
mkdir -p "$DEST"
for file in extension.js format.js metadata.json stylesheet.css; do
  cp "$ROOT/$file" "$DEST/$file"
done
cp -a "$ROOT/icons" "$ROOT/schemas" "$DEST/"
glib-compile-schemas "$DEST/schemas"
if ! gnome-extensions enable "$UUID"; then
  echo "Installed. Log out and back in to discover the extension, then: gnome-extensions enable $UUID" >&2
fi
printf 'Installed %s (using top-level ccusage and codexusage).\n' "$UUID"
printf 'Log out of Ubuntu and back in to reload the widget JavaScript. No provider re-login required if your credentials still work.\n'
printf 'Check credentials without changing them: ccusage --json && codexusage --json\n'
