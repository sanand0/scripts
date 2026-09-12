#!/usr/bin/env bash
# Log each VLC track when it starts playing. Output: ISO-8601 timestamp<TAB>MPRIS URL.

set -euo pipefail

data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/sanand-scripts"
log="$data_dir/vlc-history.tsv"
mkdir -p "$data_dir"

last_key=
format=$'{{status}}\t{{mpris:trackid}}\t{{xesam:url}}'
# playerctl buffers stdout when piped; force line buffering so each MPRIS change
# reaches the reader immediately.
stdbuf -oL playerctl --player=vlc --follow metadata --format "$format" |
while IFS=$'\t' read -r status track url; do
  # playerctl emits a blank line when VLC disappears. Stopped also marks the end
  # of a play, so replaying the same file later should create a new history row.
  if [[ -z "$status" || "$status" == Stopped ]]; then
    last_key=
    continue
  fi
  [[ "$status" == Playing && -n "$url" ]] || continue

  key="$track"$'\t'"$url"
  [[ "$key" == "$last_key" ]] && continue
  printf '%s\t%s\n' "$(date --iso-8601=seconds)" "$url" >> "$log"
  last_key="$key"
done
