# Backup Google

<!--

cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium

-->

## Generate script, 14 May 2026

Write an agent-friendly CLI `backupgoogle.py` that uses `gws` CLI and connects to my Google Chat, Calendar, Mail, and updates a local text backup of the contents.

I may be logged in using different accounts, e.g. s.anand@gramener.com / root.node@gmail.com / ... - Display the current logged-in account.

Save the data in ~/Documents/data/{email}/{chat|calendar|mail}.jsonl - one JSON object per chat message, calendar event, or email.

For chat, you may need separate calls to list spaces and list messages in each space. Feel free to maintain a chat-spaces.jsonl and update that.

The aim is to extract information that will be useful for AI agents to process the data easily and understand context. Therefore:

- Ignore attachments but include filename and metadata.
- Ignore images unless there is alt text.
- Ignore the reply part of emails bodies
- Use this as the general guidance for other fields.

Pick a (preferably flat-ish) schema fields that make it easy to filter using `jq`.

Allow command line filtering by date range or number of days.

Make this file simple, short, and maintainable.

Run this for about 3 days of data (or more) so that I can review it.

---

Rename the primary text content field to body in all cases and modify the field order so that the most important fields are the first on each line. That would be:

- mail.jsonl: time, from, subject, snippet -> body
- calendar.jsonl: time, title, attendees, description -> body
- chat.jsonl: time, sender_name (maintain a chat-users.json if required, derive this from sender), text -> body
- chat-spaces.json: lastActiveTime, displayName

Drop redundant or ID fields except for the single unique `id` of the item. Aim for compactness. Specifically:

- mail.jsonl: source, account, id, thread_id, from_email, to_email. Retain time, from, to, subject, snippet, size, message_id -> id. Add cc, bcc, attachments, only if present.
- chat.jsonl: source, chat, id, updated, spaces, space_type, space_uri, thread, sender (retain sender_name), sender_type, formatted_text. Add reactions, attachments, cards only if present.
- calendar.jsonl: same approach

Ensure that the output is always sorted latest first - even if there are gaps, i.e. if we run it for Jan and Mar but not Feb.

Re-run for all of May 2026 and let's review.

<!-- codex resume 019e25eb-0f8f-7671-9ece-cea853121e7f -->
