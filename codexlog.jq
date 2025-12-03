#!/usr/bin/env -S jq --raw-output --from-file

# Convert Codex CLI session logs to Markdown from ~/.codex/sessions/yyyy/mm/dd/session.jsonl.
# Each branch renders one event type so logs stay readable without post-processing. We only include
# context that helps reproduce or understand tool behavior and skip control-plane noise.

def h(t):        "\n\n## " + t + "\n\n";
def summary(t):  "<summary><strong>" + t + "</strong></summary>\n\n";
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
def kv(k; v):    if v then "**" + k + ":** " + v + "\n" else "" end;

. as $e
| .payload.type as $t
| if ($t == "user_message" or $t == "agent_message") then
    # Render plain chat messages so the conversation is visible.
    h($t) + ($e.payload.message // "")

elif $t == "response_item" and $e.payload.type == "message" then
    # response_item messages may arrive as fragments; stitch text parts together for readability.
    ($e.payload.content // []) as $c
    | ($c | map(.text? // .message? // "") | map(select(. != "")) | join("\n\n")) as $body
    | h($e.payload.role // "message") + ($body // $e.payload.message // "")

elif $t == "session_meta" then
    # Session-level environment to help reproduce paths and versions.
    h("session")
    + kv("id"; $e.payload.id)
    + kv("cwd"; $e.payload.cwd)
    + kv("cli"; $e.payload.cli_version)
    + kv("originator"; $e.payload.originator)

elif $t == "turn_context" then
    # Per-turn runtime context explains sandboxing, approval, and model choice when a tool fails.
    h("context")
    + kv("cwd"; $e.payload.cwd)
    + kv("model"; $e.payload.model)
    + kv("sandbox"; ($e.payload.sandbox_policy.mode // $e.payload.sandbox_policy.type // ""))
    + kv("network"; $e.payload.sandbox_policy.network_access)
    + kv("approval"; $e.payload.approval_policy)

elif $t == "agent_reasoning" then
    # Show freeform reasoning text to explain why tools are chosen.
    "\n\n<details open>"
    + summary("agent reasoning")
    + ($e.payload.text // $e.payload.message // "")
    + "\n\n</details>"

elif $t == "reasoning" then
    # Some runs emit compact reasoning summaries; surface them for context.
    "\n\n<details open>"
    + summary("reasoning")
    + ($e.payload.summary[0].text // "")
    + "\n\n</details>"

elif $t == "function_call" and ($e.payload.name // "") != "update_plan" then
    # Render tool invocations with both the command and any extra arguments; omit plan bookkeeping.
    ($e.payload.arguments? // null) as $raw
    | ( ($raw | fromjson?) // $raw // {} ) as $A
    | (if ($A | type) == "object" and $A.command? then $A.command
       elif ($A | type) == "string" then $A
       else null end) as $cmd
    | ($A | if type == "object" then del(.command?) elif type == "array" then . elif type == "string" then . else null end) as $details
    | "\n\n<details>"
    + summary("tool: " + ($e.payload.name // ""))
    + (if $cmd then
        if ($cmd | type) == "array" then code("bash"; ($cmd | join(" ")))
        else code("bash"; $cmd)
        end
      else "" end)
    + (if $details and ($details != {} ) then
        if ($details | type) == "string" then code("txt"; $details)
        else code("json"; ($details | tojson))
        end
      else "" end)
    + "\n\n</details>"

elif $t == "function_call_output" and ($e.payload.call_id as $cid | ($e.payload.name // "") != "update_plan") then
    # Show tool output and exit metadata; coerce non-string outputs to text so rendering never breaks.
    ($e.payload.output? // null) as $raw
    | ( ($raw | fromjson?) // $raw // {} ) as $O
    | (if ($O | type) == "array" then
        $O | map(.text? // .message? // tostring) | join("\n\n")
       elif ($O | type) == "object" and $O.output? then
        $O.output
       else
        $O
       end) as $body
    | ($body | if type == "string" then . else tostring end) as $text
    | "\n\n<details>"
    + summary("tool output")
    + (if ($O | type) == "object" and $O.metadata? then
        "**exit:** \($O.metadata.exit_code // "unknown") · **duration:** \($O.metadata.duration_seconds // "unknown")s\n"
      else "" end)
    + code("txt"; ($text // ""))
    + "\n\n</details>"

else empty end
