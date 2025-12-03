#!/usr/bin/env -S jq --raw-output --from-file

# Convert Claude Code session logs to Markdown from ~/.claude/projects/$path/*.jsonl.
# Keep the output self-contained for debugging and replay: show conversation, tool calls/results,
# and minimal environment context, while leaving out control-plane chatter.

def h(t):        "\n\n## " + t + "\n\n";   # Headings separate turns
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n"; # Fence code/JSON for readability
def has_text($s): ($s | test("[^[:space:]]"));             # Detect any visible text

def details($label; $body):
    # Wrap sections in collapsible blocks so long outputs do not dominate the log.
    "\n\n<details><summary><strong>" + $label + "</strong></summary>\n\n"
    + (if has_text($body) then $body + "\n\n" else "" end)
    + "</details>";

def tool_use_line($owner; $item):
    # Display a tool invocation with its input payload.
    ($owner + ": tool: " + ($item.name // "")) as $label
    | (if $item.input? then code("json"; ($item.input | tojson)) else "" end) as $body
    | details($label; $body);

def tool_result_line($owner; $item):
    # Display a tool result (string or JSON) alongside the tool_use for context.
    ($owner + ": tool result" + (if $item.tool_use_id then ": " + $item.tool_use_id else "" end)) as $label
    | (if ($item.content? // null) == null then ""
        elif ($item.content | type) == "string" then
            if ($item.content | test("[^[:space:]]")) then code("txt"; ($item.content // "")) else "" end
        else code("json"; ($item.content | tojson))
        end) as $body
    | details($label; $body);

def meta_block($e):
    # Minimal runtime context (paths, branch, identifiers, timestamps) to reproduce the run.
    {
        parentUuid: $e.parentUuid,
        isSidechain: $e.isSidechain,
        userType: $e.userType,
        cwd: $e.cwd,
        sessionId: $e.sessionId,
        version: $e.version,
        gitBranch: $e.gitBranch,
        requestId: $e.requestId,
        uuid: $e.uuid,
        timestamp: $e.timestamp
    }
    | with_entries(select(.value != null))
    | if length > 0 then details("meta"; code("json"; (.| tojson))) else "" end;

def render($owner; $content):
    # Normalize mixed content (text plus tool_use/tool_result entries) into text plus extras.
    if ($content | type) == "string" then
        {text: ($content // ""), extras: [], has_text: has_text($content // "")}
    elif ($content | type) == "array" then
        (reduce $content[] as $item (
            {text:"", extras: []};
            if $item.type == "text" then
                .text += (if has_text(.text) then "\n\n" else "" end) + ($item.text // "")
            elif $item.type == "tool_use" then
                .extras += [tool_use_line($owner; $item)]
            elif $item.type == "tool_result" then
                .extras += [tool_result_line($owner; $item)]
            else .
            end
        )) as $acc
        | $acc + {has_text: has_text($acc.text)}
    else
        {text:"", extras: [], has_text:false}
    end;

. as $e
| .type as $owner
| if ($owner == "user" or $owner == "assistant" or $owner == "system") then
    # Render only conversational events; other event types are ignored to reduce noise.
    (render($owner; .message.content)) as $parts
    | (if $parts.has_text then h($owner) + $parts.text else "" end)
    + (if ($parts.extras | length) > 0 then
        (if $parts.has_text then "\n\n" else "" end) + ($parts.extras | join("\n\n"))
      else "" end)
    + (if (.toolUseResult? != null) then
        (if $parts.has_text or ($parts.extras | length) > 0 then "\n\n" else "" end)
        + details(($owner + ": tool result: meta"); code("json"; (.toolUseResult | tojson)))
      else "" end)
    + meta_block($e)
else empty end
