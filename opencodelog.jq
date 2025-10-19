#!/usr/bin/env -S jq --raw-output --from-file

# Converts OpenCode session logs to Markdown (from `opencode export sessionID`)

def h(t):        "\n\n## " + t + "\n\n";
def summary(t):  "<summary><strong>" + t + "</strong></summary>\n\n";
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";

def has_text($s):
    if $s == null then false
    elif ($s | type) == "string" then $s | test("[^[:space:]]")
    else true
    end;

def textify($v):
    if $v == null then ""
    elif ($v | type) == "string" then $v
    else ($v | tostring)
    end;

def kv(k; v):
    textify(v) as $s
    | if has_text($s) then "**" + k + ":** " + $s + "\n" else "" end;

def details_open($label; $body; $open):
    "\n\n<details" + (if $open then " open" else "" end) + ">"
    + summary($label)
    + (if has_text($body) then $body + "\n\n" else "" end)
    + "</details>";

def details($label; $body):
    details_open($label; $body; false);

def json_block($label; $value):
    if $value == null then ""
    elif ($value | type) == "array" or ($value | type) == "object" then
        "**" + $label + ":**\n" + code("json"; ($value | tojson))
    elif ($value | type) == "string" then
        (($value | fromjson?) // null) as $maybe
        | if $maybe != null then
            "**" + $label + ":**\n" + code("json"; ($maybe | tojson))
          else
            "**" + $label + ":**\n" + code("txt"; $value)
          end
    else
        kv($label; $value)
    end;

def render_tool($role; $part):
    ($part.state // {}) as $state
    | [
        kv("status"; $state.status),
        kv("title"; $state.title),
        kv("call id"; $part.callID),
        kv("tool id"; $part.id),
        (if $state.time? then
            kv("time"; ("start " + (($state.time.start // "unknown") | tostring) + " · end " + (($state.time.end // "unknown") | tostring)))
         else "" end),
        (if $state.error? then "**error:**\n" + code("txt"; ($state.error // "")) else "" end),
        json_block("input"; $state.input),
        json_block("output"; $state.output),
        json_block("metadata"; $state.metadata)
      ] | join("") as $body
    | details(($role + ": tool: " + ($part.tool // "")); $body);

def render_reasoning($role; $part):
    if has_text($part.text // "") then
        details_open($role + ": reasoning"; $part.text // ""; true)
    else "" end;

def render_step_finish($role; $part):
    ($part.tokens // {}) as $tokens
    | (kv("cost"; $part.cost)
      + (if ($tokens | length) == 0 then "" else
            "**tokens:** input " + (($tokens.input // 0) | tostring)
            + " · output " + (($tokens.output // 0) | tostring)
            + " · reasoning " + (($tokens.reasoning // 0) | tostring) + "\n"
        end)
      + (if $tokens.cache? then
            "**cache:** read " + (($tokens.cache.read // 0) | tostring)
            + " · write " + (($tokens.cache.write // 0) | tostring) + "\n"
        else "" end)
    ) as $body
    | details($role + ": step-finish"; $body);

def render_part($role; $part):
    if $part.type == "tool" then render_tool($role; $part)
    elif $part.type == "reasoning" then render_reasoning($role; $part)
    elif $part.type == "step-finish" then render_step_finish($role; $part)
    else "" end;

def collect_text($parts):
    reduce $parts[] as $part (""; if $part.type == "text" then
        . + (if has_text(.) then "\n\n" else "" end) + ($part.text // "")
    else
        .
    end);

.messages[]
| .info.role as $role
| collect_text(.parts) as $text
| [ .parts[] | render_part($role; .) | select(has_text(.)) ] as $extras
| ($text | has_text(.)) as $has_text
| ($extras | length) as $extra_count
| if $has_text or $extra_count > 0 then
    (if $has_text then h($role) + $text else h($role) end)
    + ($extras | join(""))
  else "" end
