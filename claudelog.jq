#!/usr/bin/env -S jq --raw-output --from-file

# converts Claude Code session logs to Markdown (from ~/.claude/projects/$path/*.jsonl)

def h(t):        "\n\n## " + t + "\n\n";
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
def has_text($s): ($s | test("[^[:space:]]"));

def details($label; $body):
    "\n\n<details><summary><strong>" + $label + "</strong></summary>\n\n"
    + (if has_text($body) then $body + "\n\n" else "" end)
    + "</details>";

def tool_use_line($owner; $item):
    ($owner + ": tool: " + ($item.name // "")) as $label
    | (if $item.input? then code("json"; ($item.input | tojson)) else "" end) as $body
    | details($label; $body);

def tool_result_line($owner; $item):
    ($owner + ": tool result" + (if $item.tool_use_id then ": " + $item.tool_use_id else "" end)) as $label
    | (if ($item.content? // null) == null then ""
        elif ($item.content | type) == "string" then
            if ($item.content | test("[^[:space:]]")) then code("txt"; ($item.content // "")) else "" end
        else code("json"; ($item.content | tojson))
        end) as $body
    | details($label; $body);

def render($owner; $content):
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
    (render($owner; .message.content)) as $parts
    | (if $parts.has_text then h($owner) + $parts.text else "" end)
    + (if ($parts.extras | length) > 0 then
        (if $parts.has_text then "\n\n" else "" end) + ($parts.extras | join("\n\n"))
      else "" end)
    + (if $owner == "user" and (.toolUseResult? != null) then
        (if $parts.has_text or ($parts.extras | length) > 0 then "\n\n" else "" end)
        + details("user: tool result: meta"; code("json"; (.toolUseResult | tojson)))
      else "" end)
else empty end
