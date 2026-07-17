#!/bin/bash

# Activate mise since we need jq which is mise-installed (~50ms)
eval "$(mise env -s bash)"

# Edge's session file has sleeping-tab titles; hidden CDP tab targets provide activatable IDs.
CDP_URL=http://localhost:9222
TABS_JSON=$(/home/sanand/code/scripts/edge tabs --json --cdp-url "$CDP_URL")

if [[ $# -eq 0 ]]; then
    # List the domain, title, and ID of each browser tab, separated by tabs (column delimiter).
    echo "$TABS_JSON" | jq -r '.windows[].tabs[] | select(.cdp_id) |
      (.url | sub("^https?://"; "") | split("/")[0])
      + "\t" + .title + "\t🔑" + .cdp_id' | column -t -s $'\t'
else
    # rofi returns value the after the 🔑
    TAB_ID=$(echo -e "$*" | sed 's/.*🔑\(.*\)/\1/')

    # Activate the target via the HTTP endpoint.
    curl -s "$CDP_URL/json/activate/$TAB_ID" >/dev/null
fi
