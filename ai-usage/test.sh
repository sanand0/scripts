#!/usr/bin/env bash
# Fully offline adapter & formatting tests; never touch real credentials/network.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
SCRIPTS="$ROOT/.."
cd "$ROOT"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"
cat > "$T/bin/curl" <<'MOCK'
#!/usr/bin/env bash
set -eu
out=''; url=''
for ((i=1;i<=$#;i++)); do
  arg=${!i}
  if [[ "$arg" == -o ]]; then j=$((i+1)); out=${!j}; fi
  if [[ "$arg" == https://* ]]; then url="$arg"; fi
done
# Consume the bearer config from stdin as curl would, without printing it.
config=''
if [[ " $* " == *'--config -'* ]]; then config=$(cat); fi
if [[ $url == *'/oauth/token' ]]; then
  printf '{"access_token":"new-owned","refresh_token":"new-rotated","expires_in":28800,"scope":"user:profile user:inference"}' > "$out"
  printf 200
elif [[ $url == *'api/oauth/usage' ]]; then
  if [[ ${MOCK_CLAUDE_STATUS:-} == 401 ]]; then
    printf '{"error":"unauthorized"}' > "$out"
    printf 401
    exit 0
  fi
  if [[ -n ${MOCK_CLAUDE_ROTATE_CRED:-} && "$config" == *old-token* ]]; then
    printf '{"claudeAiOauth":{"accessToken":"new-token","refreshToken":"owned-by-claude"}}' > "$MOCK_CLAUDE_ROTATE_CRED"
    printf '{"error":"stale token"}' > "$out"
    printf 401
    exit 0
  fi
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
# Unauthenticated access should explain how to renew via Claude Code, not launch browser login.
if MOCK_CLAUDE_STATUS=401 CCUSAGE_CREDENTIALS="$T/shared.json" "$SCRIPTS/ccusage" --json > "$T/failed-out.json" 2>"$T/failed-err"; then
  echo 'ERROR: expired token unexpectedly succeeded' >&2; exit 1
fi
grep -q 'start/restart Claude Code' "$T/failed-err"
[[ "$before" == "$(sha256sum "$T/shared.json")" ]]
# If Claude Code rotates a token concurrently, retry once with its new token.
printf '{"claudeAiOauth":{"accessToken":"old-token","refreshToken":"owned-by-claude"}}' > "$T/rotating.json"
MOCK_CLAUDE_ROTATE_CRED="$T/rotating.json" CCUSAGE_CREDENTIALS="$T/rotating.json" \
  "$SCRIPTS/ccusage" --json > "$T/rotated.json"
jq -e '.windows["5h"].used_percent == 17' "$T/rotated.json" >/dev/null
jq -e '.claudeAiOauth.accessToken == "new-token"' "$T/rotating.json" >/dev/null
[[ "$before" == "$(sha256sum "$T/shared.json")" ]]
# A separate monitor login is no longer supported or needed.
if "$SCRIPTS/ccusage" --setup > "$T/setup-out" 2> "$T/setup-err"; then
  echo 'ERROR: obsolete --setup was accepted' >&2; exit 1
fi
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
# Exercise the widget with GNOME stand-ins and settings persisted outside its runtime.
AI_USAGE_TEST_STATE="$T/widget.json" node --input-type=module <<'JS'
import assert from 'node:assert/strict';
import {existsSync, readFileSync, writeFileSync} from 'node:fs';
import vm from 'node:vm';
import * as format from './format.js';
const state = process.env.AI_USAGE_TEST_STATE;
class Actor {
    constructor(options = {}) { Object.assign(this, options); this.label = {text: options}; this.menu = this; }
    add_child() {}
    addMenuItem() {}
    connect() { return 1; }
    setOrnament() {}
}
class Button extends Actor {
    constructor(extension) { super(); this._init(extension); }
    _init() {}
}
const source = readFileSync('./extension.js', 'utf8').replace(/^import .*;\n/gm, '')
    .replace('export default class', 'class') + '\nUsageIndicator;';
const reading = (provider, used) => ({provider, checked_at: new Date().toISOString(),
    windows: {'5h': {used_percent: used}, '7d': null}});
function start(responses) {
    const settings = {
        get_string: () => existsSync(state) ? readFileSync(state, 'utf8') : '{}',
        set_string: (_, value) => writeFileSync(state, value),
        get_int: () => 0, connect: () => 1,
    };
    const context = vm.createContext({...format, console, Extension: class {}, Clutter: {ActorAlign: {}},
        GObject: {registerClass: value => value}, PanelMenu: {Button},
        St: {Icon: Actor, BoxLayout: Actor, Label: Actor},
        PopupMenu: {PopupMenuItem: Actor, PopupSeparatorMenuItem: Actor, PopupBaseMenuItem: Actor,
            PopupSubMenuMenuItem: Actor, Ornament: {}},
        GLib: {build_filenamev: parts => parts.join('/'), get_home_dir: () => '/test-home',
            timeout_add_seconds: () => 1},
        Gio: {_promisify() {}, FileIcon: Actor, File: {new_for_path: path => path}, SubprocessFlags: {},
            Subprocess: class {
                static new() {
                    const response = responses.shift();
                    return {communicate_utf8_async: async () => [JSON.stringify(response), 'offline'],
                        get_successful: () => response !== null};
                }
            }},
    });
    const Indicator = vm.runInContext(source, context);
    return new Indicator({path: '.', getSettings: () => settings});
}
const settled = () => new Promise(resolve => setImmediate(resolve));
const empty = start([null, null]);
await settled();
assert.equal(empty._panel.claude['5h'].text, '—');
assert.equal(existsSync(state), false);
const good = start([reading('claude', 17), reading('codex', 0)]);
await settled();
assert.equal(good._panel.claude['5h'].text, '17%');
const saved = readFileSync(state, 'utf8');
const restarted = start([null, null]);
assert.equal(restarted._panel.claude['5h'].text, '17%'); // Visible before refresh completes.
assert.equal(restarted._panel.codex['5h'].text, '0%');
await settled();
assert.equal(readFileSync(state, 'utf8'), saved);
assert.match(restarted._details.claude.status.text, /Last good: .*Error: offline/);
const mixed = start([reading('claude', 23), null]);
await settled();
assert.equal(mixed._panel.claude['5h'].text, '23%');
assert.equal(mixed._panel.codex['5h'].text, '0%');
const invalid = start([{provider: 'claude'}, reading('claude', 99)]);
await settled();
assert.equal(invalid._panel.claude['5h'].text, '23%');
assert.equal(invalid._panel.codex['5h'].text, '0%');
assert.deepEqual(JSON.parse(readFileSync(state, 'utf8')), JSON.parse(JSON.stringify(mixed.snapshots)));
JS
echo 'PASS: Claude shared read-only, expired-token guidance, concurrent rotation, Codex RPC fallback, panel formatting, persistent widget fallback'
