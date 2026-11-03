#!/bin/bash
# Rofi browser-tab mode: list Edge CDP tabs, switch, or show tab actions.
set -euo pipefail
CDP_URL=http://localhost:9222

if [[ "${1:-}" == --actions ]]; then
    id="$2"
    index="$(printf '%s\n' "Switch to tab" "Copy URL" "Copy title" "Close tab" |
        rofi -dmenu -i -no-custom -format i -p 'Browser tab')" || exit 0
    case "$index" in
        0) curl -fsS "$CDP_URL/json/activate/$id" >/dev/null ;;
        1|2)
            eval "$(mise env -s bash)"
            field=url
            [[ "$index" == 2 ]] && field=title
            curl -fsS "$CDP_URL/json/list" |
                jq -r --arg id "$id" --arg field "$field" '.[] | select(.id == $id) | .[$field]' |
                xclip -selection clipboard -in
            ;;
        3) curl -fsS "$CDP_URL/json/close/$id" >/dev/null ;;
    esac
    exit 0
fi

if [[ "${ROFI_RETV:-0}" == 0 ]]; then
    # The session file has sleeping-tab titles; CDP identifies activatable tabs.
    eval "$(mise env -s bash)"
    printf '\0use-hot-keys\x1ftrue\n\0no-custom\x1ftrue\n'
    "$HOME/code/scripts/edge" tabs --json --cdp-url "$CDP_URL" |
        jq -r '.windows[].tabs[] | select(.cdp_id) |
          (.url | sub("^https?://"; "") | split("/")[0])
          + "  " + (.title | gsub("[\r\n\t]"; " "))
          + "\u0000info\u001f" + .cdp_id'
else
    id="${ROFI_INFO:-${*##*🔑}}"
    if ((ROFI_RETV >= 10)); then
        setsid "$0" --actions "$id" >/dev/null 2>&1 &
        if [[ -n "${ROFI_PICKER_PIDFILE:-}" && -r "$ROFI_PICKER_PIDFILE" ]]; then
            read -r pid < "$ROFI_PICKER_PIDFILE"
            [[ "$pid" =~ ^[0-9]+$ ]] && kill -TERM "$pid" 2>/dev/null || true
        fi
    else
        curl -fsS "$CDP_URL/json/activate/$id" >/dev/null
    fi
fi
