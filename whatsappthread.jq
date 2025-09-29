#!/usr/bin/env -S jq --raw-output --compact-output --from-file

# Converts https://tools.s-anand.net/whatsappscraper/ JSON into LLM-friendly JSONL + thread_id + urls[]
# https://chatgpt.com/c/68d8c76f-b550-8328-93f1-b1bc03a2c243
#
# Usage:
#   whatsappthread.jq input.json > output.jsonl

# Build an index: messageId -> message object
def by_id:
  reduce .[] as $m ({}; .[$m.messageId] = $m);

# Compute the root of a quote/reply chain (thread_id)
def thread_root($by; $id):
  if $id == null then null
  else
    ($by[$id] // {}) as $m
    | ($m.quoteMessageId // null) as $parent
    | if $parent == null then $id else thread_root($by; $parent) end
  end;

# Extract brute-force URLs from text by tokenizing
def url_list($t):
  ($t // "")
  | split(" ")
  | map(select(test("^(https?://|www\\.)"))) ;

# MAIN
. as $arr
| ($arr | by_id) as $by
| $arr[]
| {
    id: (.messageId // null),
    chat_id: (.userId // null),
    ts: (.time // null),
    type: (if (.isSystemMessage // false) then "system"
           elif (.isRecalled // false) then "recalled"
           else "message" end),
    author: { name: (.author // null), phone: (.authorPhone // null) },
    text_raw: (.text // null),
    reply_to_id: (.quoteMessageId // null),
    reply_to: (if .quoteMessageId then
                 { author: (.quoteAuthor // null),
                   phone: (.quoteAuthorPhone // null),
                   text: (.quoteText // null) }
               else null end),
    thread_id: thread_root($by; (.messageId // null)),
    urls: url_list(.text)
  }
