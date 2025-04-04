#!/bin/bash
# Fetch JSON list of targets from Edge (remote debugging must be enabled)
TABS_JSON=$(curl -s http://localhost:9222/json | jq -r 'map(select(.type=="page") | {id: .id, title: .title, url: .url})')

if [[ $# -eq 0 ]]; then
    # List the domain, title, and ID of each browser tab, separated by tabs (column delimiter).
    echo "$TABS_JSON" | jq -r '.[] |
      (.url | capture("https?://(?<domain>[^/]+)") | .domain)
      + "\t" + .title + "\t🔑" + .id' | column -t -s $'\t'
else
    # rofi returns the after the 🔑
    TAB_ID=$(echo -e "$*" | sed 's/.*🔑\(.*\)/\1/')

    # Activate the target via the HTTP endpoint.
    curl -s "http://localhost:9222/json/activate/$TAB_ID" >/dev/null
fi
