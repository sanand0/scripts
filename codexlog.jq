#!/usr/bin/env -S jq --raw-output --from-file

# Convert Codex CLI session logs to Markdown from ~/.codex/sessions/yyyy/mm/dd/session.jsonl.
# Keep the visible output reviewer-friendly: show the conversation and runtime context inline,
# collapse tools and their outputs with enough summary text to decide what matters to open.
# Set CODEXLOG_BRIEF=1 to truncate very large tool outputs; default mode preserves full output.

def h($t): "\n\n## " + $t + "\n\n";
def summary($t): "<summary><strong>" + $t + "</strong></summary>\n\n";
def code($lang; $text): "```" + $lang + "\n" + ($text // "") + "\n```\n";

def textify($value):
  if $value == null then ""
  elif ($value | type) == "string" then $value
  else ($value | tostring)
  end;

def has_text($value):
  (textify($value) | test("[^[:space:]]"));

def kv($key; $value):
  textify($value) as $text
  | if has_text($text) then
      "**" + $key + ":** " + $text + "\n"
    else
      ""
    end;

def compact_ws:
  gsub("[[:space:]\n\r\t]+"; " ")
  | sub("^ "; "")
  | sub(" $"; "");

def shorten($limit):
  . as $text
  | if ($text | length) <= $limit then
      $text
    elif $limit <= 3 then
      .[0:$limit]
    else
      .[0:($limit - 3)] + "..."
    end;

def preview_text($value; $limit):
  textify($value)
  | compact_ws
  | shorten($limit);

def brief_mode:
  ((env.CODEXLOG_BRIEF // "") | ascii_downcase) as $value
  | ($value == "1" or $value == "true" or $value == "yes" or $value == "on");

def details($label; $body; $open):
  "\n\n<details" + (if $open then " open" else "" end) + ">"
  + summary($label)
  + (if has_text($body) then $body + "\n\n" else "" end)
  + "</details>";

def parse_arguments($raw):
  (($raw | fromjson?) // $raw // {});

def command_text($args):
  if ($args | type) == "object" and $args.cmd? then
    textify($args.cmd)
  elif ($args | type) == "object" and $args.command? then
    textify($args.command)
  elif ($args | type) == "object" and $args.tool_uses? then
    (($args.tool_uses | length | tostring) + " parallel calls")
  elif ($args | type) == "string" then
    $args
  else
    ""
  end;

def details_value($args):
  if ($args | type) == "object" then
    ($args | del(.cmd?, .command?))
  elif ($args | type) == "string" then
    null
  else
    $args
  end;

def render_details_value($value):
  if $value == null or $value == {} or $value == [] then
    ""
  elif ($value | type) == "string" then
    if has_text($value) then code("txt"; $value) else "" end
  else
    code("json"; ($value | tojson))
  end;

def reasoning_text($payload):
  (
    ($payload.summary // [])
    | map(.text? // .message? // "")
    | map(select(has_text(.)))
    | join("\n\n")
  ) as $summary_text
  | if has_text($summary_text) then
      $summary_text
    else
      ($payload.text // $payload.message // "")
    end;

def parse_tool_output($raw):
  parse_arguments($raw) as $parsed
  | (
      if ($parsed | type) == "array" then
        ($parsed | map(.text? // .message? // tostring) | join("\n\n"))
      elif ($parsed | type) == "object" and $parsed.output? then
        textify($parsed.output)
      else
        textify($parsed)
      end
    ) as $text
  | ($text | split("\n")) as $lines
  | if (
      ($lines | length) > 0
      and (
        ($lines[0] | startswith("Chunk ID: "))
        or ($lines[0] | startswith("Wall time: "))
        or ($lines[0] | startswith("Process "))
      )
    ) then
      {
        chunk: ([ $lines[] | select(startswith("Chunk ID: ")) | sub("^Chunk ID: "; "") ][0] // null),
        wall: ([ $lines[] | select(startswith("Wall time: ")) | sub("^Wall time: "; "") ][0] // null),
        exit: ([ $lines[] | select(startswith("Process exited with code ")) | sub("^Process exited with code "; "") ][0] // null),
        session_id: ([ $lines[] | select(startswith("Process running with session ID ")) | sub("^Process running with session ID "; "") ][0] // null),
        tokens: ([ $lines[] | select(startswith("Original token count: ")) | sub("^Original token count: "; "") ][0] // null),
        body: (
          if ($text | contains("\nOutput:\n")) then
            ($text | split("\nOutput:\n") | .[1:] | join("\nOutput:\n"))
          else
            ""
          end
        )
      }
    else
      { body: $text }
    end;

def first_nonblank_line($text):
  ([ ($text | split("\n"))[] | select(test("[^[:space:]]")) ][0] // "");

def session_key($payload):
  {
    id: ($payload.id // null),
    time: ($payload.timestamp // null),
    cwd: ($payload.cwd // null),
    cli: ($payload.cli_version // null),
    source: ($payload.source // null),
    provider: ($payload.model_provider // null),
    originator: ($payload.originator // null)
  };

def context_key($payload):
  {
    cwd: ($payload.cwd // null),
    date: ($payload.current_date // null),
    timezone: ($payload.timezone // null),
    model: ($payload.model // null),
    sandbox: ($payload.sandbox_policy.mode // $payload.sandbox_policy.type // null),
    network: ($payload.sandbox_policy.network_access // null),
    approval: ($payload.approval_policy // null)
  };

def brief_text($text):
  if (brief_mode | not) then
    $text
  else
    ($text // "") as $body
    | ($body | split("\n")) as $lines
    | ($body | length) as $chars
    | if $chars <= 5000 and ($lines | length) <= 140 then
        $body
      elif ($lines | length) > 140 then
        (
          ($lines[0:80]
           + ["[... " + ((($lines | length) - 110) | tostring) + " lines omitted; rerun without CODEXLOG_BRIEF for full output ...]"]
           + $lines[-30:])
          | join("\n")
        )
      else
        (
          $body[0:3500]
          + "\n[... " + (($chars - 4700) | tostring) + " characters omitted; rerun without CODEXLOG_BRIEF for full output ...]\n"
          + $body[-1200:]
        )
      end
  end;

def tool_call_label($name; $command_preview):
  "tool: " + $name
  + (if has_text($command_preview) then " - " + $command_preview else "" end);

def tool_output_label($call; $parts):
  (
    [ if ($parts.exit // null) != null then "exit " + $parts.exit else empty end,
      if ($parts.wall // null) != null then $parts.wall else empty end,
      if ($parts.session_id // null) != null then "session " + $parts.session_id else empty end
    ] | join(" · ")
  ) as $status
  | preview_text(first_nonblank_line($parts.body // ""); 60) as $body_preview
  | "tool output: " + ($call.name // "unknown")
    + (if has_text($call.command_preview // "") then " - " + $call.command_preview else "" end)
    + (if has_text($status) then " [" + $status + "]" else "" end)
    + (if has_text($body_preview) then " -> " + $body_preview else "" end);

def tool_output_body($parts):
  (
    [ kv("exit"; $parts.exit),
      kv("wall"; $parts.wall),
      kv("session"; $parts.session_id),
      kv("tokens"; $parts.tokens)
    ] | join("")
  ) as $meta
  | $meta
    + (if has_text($parts.body // "") then code("txt"; brief_text($parts.body // "")) else "" end);

def render_event($event; $state):
  $event.type as $type
  | ($event.payload.type // "") as $payload_type
  | if $type == "event_msg" and ($payload_type == "user_message" or $payload_type == "agent_message") then
      h($payload_type) + ($event.payload.message // "")

    elif $type == "session_meta" then
      if $state.emit_session then
        h("session")
        + kv("id"; $event.payload.id)
        + kv("time"; $event.payload.timestamp)
        + kv("cwd"; $event.payload.cwd)
        + kv("cli"; $event.payload.cli_version)
        + kv("source"; $event.payload.source)
        + kv("provider"; $event.payload.model_provider)
        + kv("originator"; $event.payload.originator)
      else
        ""
      end

    elif $type == "turn_context" then
      if $state.emit_context then
        h("context")
        + kv("cwd"; $event.payload.cwd)
        + kv("date"; $event.payload.current_date)
        + kv("timezone"; $event.payload.timezone)
        + kv("model"; $event.payload.model)
        + kv("sandbox"; ($event.payload.sandbox_policy.mode // $event.payload.sandbox_policy.type // ""))
        + kv("network"; $event.payload.sandbox_policy.network_access)
        + kv("approval"; $event.payload.approval_policy)
      else
        ""
      end

    elif $type == "response_item" and $payload_type == "reasoning" then
      reasoning_text($event.payload) as $text
      | if has_text($text) then
          details("reasoning"; $text; true)
        else
          ""
        end

    elif $type == "agent_reasoning" then
      reasoning_text($event.payload) as $text
      | if has_text($text) then
          details("agent reasoning"; $text; true)
        else
          ""
        end

    elif $type == "response_item" and $payload_type == "function_call" then
      ($event.payload.name // "") as $name
      | if $name == "update_plan" then
          ""
        else
          parse_arguments($event.payload.arguments? // null) as $args
          | command_text($args) as $command
          | preview_text($command; 80) as $command_preview
          | render_details_value(details_value($args)) as $detail_block
          | details(
              tool_call_label($name; $command_preview);
              (if has_text($command) then code("bash"; $command) else "" end) + $detail_block;
              false
            )
        end

    elif $type == "response_item" and $payload_type == "function_call_output" then
      ($state.calls[$event.payload.call_id] // null) as $call
      | if ($call.name // "") == "update_plan" then
          ""
        else
          parse_tool_output($event.payload.output? // null) as $parts
          | details(
              tool_output_label(($call // {name: "unknown", command_preview: ""}); $parts);
              tool_output_body($parts);
              (($parts.exit // "0") != "0")
            )
        end

    else
      ""
    end;

foreach (., inputs) as $event (
  {
    calls: {},
    event: null,
    emit_session: false,
    emit_context: false,
    last_session: null,
    last_context: null
  };
  (
    .event = $event
    | .emit_session = false
    | .emit_context = false
    | (
        if $event.type == "response_item" and ($event.payload.type // "") == "function_call" then
          parse_arguments($event.payload.arguments? // null) as $args
          | .calls[$event.payload.call_id] = {
              name: ($event.payload.name // ""),
              command_preview: (preview_text(command_text($args); 80))
            }
        else
          .
        end
      )
    | (
        if $event.type == "session_meta" then
          session_key($event.payload) as $key
          | .emit_session = ($key != .last_session)
          | .last_session = $key
        elif $event.type == "turn_context" then
          context_key($event.payload) as $key
          | .emit_context = ($key != .last_context)
          | .last_context = $key
        else
          .
        end
      )
  );
  render_event(.event; .)
)
| select(has_text(.))
