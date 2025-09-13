#!/usr/bin/env bash

# A shortcut to convert voice to code and paste in previous window.
#   - Edit system prompt at ~/Dropbox/notes/talkcode.md
#   - Press Ctrl+Alt+0
#   - Speak
#   - Press Q
#   - Generated code is pasted in the most recent window

# Setup: In Settings > Keyboard > Custom Shortcuts, add a shortcut:
#   Name: Talk Code
#   Shortcut: Ctrl+Alt+0
#   Command: bash -lc 'ACTIVE=$(xdotool getactivewindow); gnome-terminal --zoom=2 --geometry=80x10 --wait -- bash -lc "ACTIVE_WIN=$ACTIVE /home/sanand/code/scripts/talkcode.sh"'
#
# Why gnome-terminal? It's already installed and I did not research alternatives.

set -euo pipefail

AUDIO="${XDG_CACHE_HOME:-$HOME/.cache}/talkcode/rec.opus"
mkdir -p "$(dirname "$AUDIO")"

echo "Recording… press Q to stop." >&2
# Mic only, 16 kHz mono, voice filtering, fast Opus
ffmpeg -hide_banner -v error \
  -f pulse -i default \
  -ac 1 -ar 16000 \
  -af "highpass=f=100,lowpass=f=6000" \
  -c:a libopus -b:a 16k -vbr on \
  -compression_level 2 -application voip -frame_duration 60 \
  -y "$AUDIO"

echo "Processing…" >&2

# Read system prompt. Why from Dropbox? For back-up and phone-editing.
SYSTEM_TEXT="$(<"$HOME/Dropbox/notes/talkcode.md")"

# Why hard-code llm path? I haven't set up llm system-wide yet.
# Why Gemini not OpenAI? As of 11 Sep 2025: No Opus, `llm` rejects -a with audio
/home/sanand/apps/llm/.venv/bin/llm -m gemini-2.5-flash -a "$AUDIO" -s "$SYSTEM_TEXT" \
  | tee /dev/tty \
  | awk 'BEGIN{f=0} /```/{f=!f; next} f{buf=buf$0"\n"} END{print buf}' \
  | xclip -selection clipboard

if [ -n "${ACTIVE_WIN:-}" ]; then
  # Bring last window to foreground
  # Why not autokey? xdotool keeps everything in one script
  xdotool windowactivate --sync "$ACTIVE_WIN"
  sleep 0.08
  # Paste from clipboard
  xdotool key --clearmodifiers ctrl+shift+v
fi

sleep 5
