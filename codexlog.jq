#!/usr/bin/env -S jq --raw-output --from-file

# Converts Codex CLI session logs to Markdown (from ~/.codex/sessions/yyyy/mm/dd/session.jsonl)

def h(t):        "\n\n## " + t + "\n\n";
def summary(t):  "<summary><strong>" + t + "</strong></summary>\n\n";
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
def kv(k; v):    if v then "**" + k + ":** " + v + "\n" else "" end;

. as $e
| .payload.type as $t
| if ($t == "user_message" or $t == "agent_message") then
    h($t) + ($e.payload.message // "")

elif $t == "agent_reasoning" then
    "\n\n<details>"
    + summary("agent reasoning")
    + ($e.payload.text // $e.payload.message // "")
    + "\n\n</details>"

elif $t == "function_call" then
    ($e.payload.arguments? | fromjson? // {}) as $A
    | "\n\n<details>"
    + summary("tool: " + ($e.payload.name // ""))
    + (if $A.command? then code("bash"; ($A.command | join(" "))) else "" end)
    + "\n\n</details>"

elif $t == "function_call_output" then
    ($e.payload.output? | fromjson? // {}) as $O
    | "\n\n<details>"
    + summary("tool output")
    + (if $O.metadata? then
        "**exit:** \($O.metadata.exit_code // "unknown") · **duration:** \($O.metadata.duration_seconds // "unknown")s\n"
    else "" end)
    + code("txt"; ($O.output // ""))
    + "\n\n</details>"

else empty end
