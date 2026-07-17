#!/bin/bash

# Activate mise since we need jq which is mise-installed (~50ms)
eval "$(mise env -s bash)"

# CDP's hidden "tab" targets include sleeping tabs; /json only lists live page targets.
CDP_URL=http://localhost:9222
CDP_WS=$(curl -fsS "$CDP_URL/json/version" | jq -r .webSocketDebuggerUrl)
TABS_JSON=$(printf '%s\n' '{"id":1,"method":"Target.getTargets","params":{"filter":[{"type":"tab","exclude":false},{"exclude":true}]}}' |
    websocat -1 "$CDP_WS" | jq '.result.targetInfos')

if [[ $# -eq 0 ]]; then
    # List the domain, title, and ID of each browser tab, separated by tabs (column delimiter).
    echo "$TABS_JSON" | jq -r '.[] | select(.embedderData.tabStripIndex? != null) |
      (.url | sub("^https?://"; "") | split("/")[0])
      + "\t" + .title + "\t🔑" + .targetId' | column -t -s $'\t'
else
    # rofi returns value the after the 🔑
    TAB_ID=$(echo -e "$*" | sed 's/.*🔑\(.*\)/\1/')

    # Activate the target via the HTTP endpoint.
    curl -s "$CDP_URL/json/activate/$TAB_ID" >/dev/null
fi
