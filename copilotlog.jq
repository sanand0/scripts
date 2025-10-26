#!/usr/bin/env -S jq --raw-output --from-file

# Converts GitHub Copilot session logs to Markdown (from ~/.copilot/session-state/*.jsonl)

def h(t):        "\n\n## " + t + "\n\n";
def summary(t):  "<summary><strong>" + t + "</strong></summary>\n\n";
def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
def has_text($s): ($s // "" | test("[^[:space:]]"));
def kv(k; v):    if v then "**" + k + ":** " + v + "\n" else "" end;
def bool_text(v): if v == null then null elif v then "true" else "false" end;

def details($label; $body; $open):
    "\n\n<details" + (if $open then " open" else "" end) + ">"
    + summary($label)
    + (if has_text($body) then $body + "\n\n" else "" end)
    + "</details>";

. as $e
| .type as $t
| if $t == "session.start" then
    h("session.start")
    + kv("sessionId"; .data.sessionId)
    + kv("start"; .data.startTime)
    + kv("producer"; .data.producer)
    + kv("copilotVersion"; .data.copilotVersion)

  elif $t == "session.info" then
    h("session.info")
    + kv("infoType"; .data.infoType)
    + (.data.message // "")

  elif $t == "session.resume" then
    h("session.resume")
    + kv("resumeTime"; .data.resumeTime)
    + kv("eventCount"; (.data.eventCount | tostring))

  elif $t == "session.model_change" then
    h("session.model_change")
    + kv("newModel"; .data.newModel)

  elif $t == "user.message" then
    h("user")
    + (.data.content // "")

  elif $t == "assistant.message" then
    (.data.toolRequests // []) as $reqs
    | (.data.content // "") as $text
    | (has_text($text)) as $has_text
    | if (($has_text | not) and (($reqs | length) == 0)) then
        ""
      else
        h("assistant")
        + (if $has_text then $text else "" end)
        + ($reqs
            | map(
                details(
                  "tool request: " + (.name // "")
                    + (if (.toolCallId // "") != "" then " (" + .toolCallId + ")" else "" end);
                  code("json"; (.arguments | tojson));
                  false
                )
              )
            | join("")
          )
      end

  elif $t == "tool.execution_start" then
    details(
      "tool start: " + (.data.toolName // "")
        + (if (.data.toolCallId // "") != "" then " (" + .data.toolCallId + ")" else "" end);
      code("json"; (.data.arguments | tojson));
      false
    )

  elif $t == "tool.execution_complete" then
    (
      kv("success"; bool_text(.data.success))
      + (if .data.result? == null then ""
         elif (.data.result.content? // null) != null then
           code("txt"; .data.result.content)
         else
           code("json"; (.data.result | tojson))
         end)
    ) as $body
    | details(
        "tool result: " + (.data.toolCallId // "");
        $body;
        false
      )

  elif $t == "abort" then
    h("abort")
    + kv("reason"; .data.reason)

  else empty end
