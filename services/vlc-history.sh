#!/usr/bin/env bash
# Log each VLC track when it starts playing. Output: timestamp, path, tool.

set -euo pipefail

log="$HOME/Music/music-history.tsv"

last_key=
format=$'{{status}}\t{{mpris:trackid}}\t{{xesam:url}}'

vlc_ready() {
  dbus-send --session --print-reply \
    --dest=org.mpris.MediaPlayer2.vlc \
    /org/mpris/MediaPlayer2 \
    org.freedesktop.DBus.Peer.Ping \
    >/dev/null 2>&1
}

record() {
  local status=$1 track=$2 url=$3 key path music_dir
  if [[ "$status" == Stopped ]]; then
    last_key=
    return
  fi
  [[ "$status" == Playing && -n "$url" ]] || return
  key="$track"$'\t'"$url"
  [[ "$key" == "$last_key" ]] && return
  path=${url#file://}
  printf -v path '%b' "${path//%/\\x}"
  music_dir="$HOME/Music/"
  case "$path" in
    "$music_dir"*) path=${path#"$music_dir"} ;;
  esac
  printf '%s\t%s\tvlc\n' "$(date --iso-8601=seconds)" "$path" >> "$log"
  last_key="$key"
}

while true; do
  # Attach only after VLC appears. A follower started before fast launches such
  # as play-music can miss their initial metadata event.
  gdbus wait --session org.mpris.MediaPlayer2.vlc
  while vlc_ready; do
    line=$(playerctl --player=vlc metadata --format "$format" 2>/dev/null || true)
    IFS=$'\t' read -r status track url <<<"$line"
    if [[ -n "$status" ]]; then
      record "$status" "$track" "$url"
      break
    fi
    sleep 0.05
  done
  vlc_ready || continue

  # playerctl does not reconnect after VLC exits. Restart it when its blank
  # disappearance event arrives so the next VLC instance is followed.
  coproc watcher { exec stdbuf -oL playerctl --player=vlc --follow metadata --format "$format"; }
  watcher_pid=$watcher_PID
  disappeared=false
  while IFS=$'\t' read -r status track url; do
    if [[ -z "$status" ]]; then
      last_key=
      disappeared=true
      break
    fi
    record "$status" "$track" "$url"
  done <&"${watcher[0]}"
  kill "$watcher_pid" 2>/dev/null || true
  wait "$watcher_pid" 2>/dev/null || true
  "$disappeared" || sleep 1
done
