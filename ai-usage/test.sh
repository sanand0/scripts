#!/usr/bin/env bash
# Fully offline adapter & formatting tests; never touch real credentials/network.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
SCRIPTS="$ROOT/.."
cd "$ROOT"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin" "$T/profile"
cat > "$T/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -eu
out=''; url=''
for ((i=1;i<=$#;i++)); do
  arg=${!i}
  if [[ "$arg" == -o ]]; then j=$((i+1)); out=${!j}; fi
  if [[ "$arg" == https://* ]]; then url="$arg"; fi
done
# Consume the credential stream to mirror curl --config - behavior.
if [[ " $* " == *'--config -'* ]]; then cat >/dev/null; fi
if [[ $url == *'/oauth/token' ]]; then
  printf '{"access_token":"new-owned","refresh_token":"new-rotated","expires_in":28800,"scope":"user:profile user:inference"}' > "$out"
  printf 200
elif [[ $url == *'api/oauth/usage' ]]; then
  printf '{"five_hour":{"utilization":17,"resets_at":"2026-10-12T09:09:59Z"},"seven_day":{"utilization":21,"resets_at":"2026-10-15T10:00:00Z"}}' > "$out"
  printf 200
elif [[ $url == *'/wham/usage' ]]; then
  cp "$MOCK_CODEX_RESPONSE" "$out"
  printf %s "${MOCK_CODEX_STATUS:-200}"
else
  echo "unexpected URL: $url" >&2; exit 1
fi
MOCK
cat > "$T/bin/codex" <<'MOCK'
#!/usr/bin/env bash
[[ ${1:-} == app-server ]] || exit 1
while IFS= read -r line; do
  if [[ "$line" == *'"id":3'* ]]; then
    printf '{"id":3,"result":{"rateLimits":{"primary":{"usedPercent":22,"windowDurationMins":300,"resetsAt":1791810000},"secondary":{"usedPercent":44,"windowDurationMins":10080,"resetsAt":1792400000}}}}\n'
    break
  fi
done
MOCK
chmod +x "$T/bin/curl" "$T/bin/codex"
export PATH="$T/bin:$PATH"
cat > "$T/shared.json" <<'EOF_SHARED'
{"claudeAiOauth":{"accessToken":"shared-access","refreshToken":"shared-refresh","expiresAt":0,"scopes":["user:profile"]}}
EOF_SHARED
before=$(sha256sum "$T/shared.json")
CCUSAGE_CREDENTIALS="$T/shared.json" "$SCRIPTS/ccusage" --json > "$T/claude.json"
jq -e '.provider=="claude" and .windows["5h"].used_percent==17 and .windows["7d"].used_percent==21' "$T/claude.json" >/dev/null
[[ "$before" == "$(sha256sum "$T/shared.json")" ]]
# Own profile, expired, should refresh and atomically rotate only own credentials.
cat > "$T/profile/.credentials.json" <<'EOF_OWNED'
{"claudeAiOauth":{"accessToken":"old-owned","refreshToken":"old-rotated","expiresAt":1,"scopes":["user:profile"]}}
EOF_OWNED
chmod 600 "$T/profile/.credentials.json"
CCUSAGE_DIR="$T/profile" "$SCRIPTS/ccusage" --json > "$T/claude-owned.json"
jq -e '.claudeAiOauth.accessToken=="new-owned" and .claudeAiOauth.refreshToken=="new-rotated" and .claudeAiOauth.expiresAt>1000000000000' "$T/profile/.credentials.json" >/dev/null
[[ "$before" == "$(sha256sum "$T/shared.json")" ]]
# Direct Codex HTTP: identify window durations instead of assuming primary = 5h.
echo '{"rate_limit":{"primary_window":{"used_percent":1,"reset_at":1792400000,"limit_window_seconds":604800},"secondary_window":{"used_percent":0,"reset_at":1791810000,"limit_window_seconds":18000}}}' > "$T/codex.json"
echo '{"tokens":{"access_token":"fake","account_id":"fake"}}' > "$T/auth.json"
export MOCK_CODEX_RESPONSE="$T/codex.json"
CODEXUSAGE_AUTH="$T/auth.json" "$SCRIPTS/codexusage" --json > "$T/codex-out.json"
jq -e '.windows["5h"].used_percent==0 and .windows["7d"].used_percent==1' "$T/codex-out.json" >/dev/null
# No 5h window must be null rather than accidentally mislabeling 7d.
echo '{"rate_limit":{"primary_window":{"used_percent":9,"reset_at":1792400000,"limit_window_seconds":604800},"secondary_window":null}}' > "$T/codex.json"
CODEXUSAGE_AUTH="$T/auth.json" "$SCRIPTS/codexusage" --json > "$T/codex-out.json"
jq -e '.windows["5h"]==null and .windows["7d"].used_percent==9' "$T/codex-out.json" >/dev/null
# Codex HTTP 401 -> RPC result, with native refresh ownership.
export MOCK_CODEX_STATUS=401
CODEX_HOME="$T" "$SCRIPTS/codexusage" --json > "$T/codex-out.json"
jq -e '.windows["5h"].used_percent==22 and .windows["7d"].used_percent==44' "$T/codex-out.json" >/dev/null
# Independent pure JS tests for panel formatting.
node --input-type=module <<'JS'
import assert from 'node:assert/strict';
import {countdown,percent,windows,remaining,quotaTone,resetTone} from './format.js';
assert.equal(countdown(200*3600, 200*3600-2*3600-3*60), '2:03');
assert.equal(countdown(500000,500000-2*86400-3*3600), '2d 3h');
assert.equal(countdown(1,3), 'due now');
assert.equal(countdown(NaN), 'unknown');
assert.equal(percent({used_percent:0}), '0%');
assert.equal(windows({windows:{'5h':{used_percent:17},'7d':{used_percent:21}}}), '17% | 21%');
assert.equal(windows(null), '— | —');
assert.equal(remaining(200*3600,200*3600-17*60), '0:17 m');
assert.equal(remaining(10*86400,10*86400-(3*86400+3600)), '3d 1h');
for (const [value,tone] of [[0,'green'],[69.9,'green'],[70,'amber'],[89.9,'amber'],[90,'red'],[100,'red'],[NaN,'muted']])
    assert.equal(quotaTone(value),tone);
for (const [dur,hours,tone] of [['5h',2,'green'],['5h',1,'amber'],['5h',0.5,'red'],['7d',25,'green'],['7d',24,'amber'],['7d',12,'red'],['7d',-1,'red']])
    assert.equal(resetTone(dur, hours*3600, 0),tone);
assert.equal(resetTone('5h',NaN), 'muted');
// UI contract: panel quota color follows reset time; popup date remains neutral.
import {readFileSync} from 'node:fs';
const ext = readFileSync('./extension.js', 'utf8');
const css = readFileSync('./stylesheet.css', 'utf8');
assert.match(ext, /this\._panel\[provider\.key\]\[duration\]/);
assert.match(ext, /panelTone = status \|\| !Number\.isFinite\(used\) \? 'muted' : timeTone/);
assert.match(ext, /fields\.time\.style_class/);
assert.match(ext, /fields\.date\.text/);
assert.match(css, /min-width: 360px/);
assert.match(css, /ai-usage-status \{ font-size: 12px/);
JS
echo 'PASS: Claude shared read-only, dedicated rotation, Codex duration mapping/RPC fallback, panel formatting'
