# Backup Google

## Migrate emails, 03 Jun 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

My email ID used to be `s.anand@gramener.com` but because of a Straive re-branding exercise it is now `s.anand@straive.com`. It's the same account - just a different email ID.

`backupgoogle.py` used to update the archive at `/home/sanand/Documents/data/s.anand@gramener.com/` but now it updates `/home/sanand/Documents/data/s.anand@straive.com/`.

Merge these archives into `/home/sanand/Documents/data/s.anand@straive.com/`. That is all contents of the former should be present in the latter, with no duplicates. The `backupgoogle.py` script should continue to work with the new email ID.

Ensure you make backups before you do this. Test that there are no duplicates and all contents of the former AND latter are present in final archives.

It's possible that some IDs (e.g. the email ID or other IDs) may change due to the transition. If these are not independently meaningful and they can be transformed (e.g. all you need to do is replace s.anand@gramener.com with s.anand@straive.com and that'll resolve conflicts), then do that.

If there are any other problems you see, think about how best to resolve them and ask me the most important questions in the clearest way, with examples, so that I can guide you.

Make sure we can revert to the original state if needed.

No need to run `backupgoogle.py`.

---

Run `backupgoogle.py` with a few variations (e.g. different dates / filters) to test that it updates the new archive correctly and doesn't create duplicates.
For example, you might test for a range we already have data for and confirm that new new rows are created.
There may be other tests you could think of, if required.

<!-- codex resume 019e8d66-b8e1-7aa3-9cd7-545bc612c880 --yolo -->

## Allow scope failures, 22 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

If gws fails with insufficient authentication scopes, allow it to continue and just print the error.
This is because I may not have all the scopes enabled for all accounts, and I want to get whatever data I can instead of failing completely.

```
error[api]: Request had insufficient authentication scopes.
│ /home/sanand/code/scripts/backupgoogle.py:126 in gws_json                                                                                                      │
│                                                                                                                                                                │
│   123                                                                                                                                                          │
│   124                                                                                                                                                          │
│   125 def gws_json(args: list[str], *, config_dir: str = "") -> Any:                                                                                           │
│ ❱ 126 │   text = run_gws([*args, "--format", "json"], config_dir=config_dir).strip()                                                                           │
│   127 │   try:                                                                                                                                                 │
│   128 │   │   return json.loads(text or "{}")                                                                                                                  │
│   129 │   except json.JSONDecodeError:                                                                                                                         │
│                                                                                                                                                                │
│ /home/sanand/code/scripts/backupgoogle.py:121 in run_gws                                                                                                       │
│                                                                                                                                                                │
│   118 │   if stderr := useful_stderr(result.stderr):                                                                                                           │
│   119 │   │   eprint(stderr)                                                                                                                                   │
│   120 │   if result.returncode:                                                                                                                                │
│ ❱ 121 │   │   raise subprocess.CalledProcessError(result.returncode, ["gws", *args], result.stdout, result.stderr)                                             │
│   122 │   return result.stdout                                                                                                                                 │
│   123                                                                                                                                                          │
│   124                                                                                                                                                          │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
CalledProcessError: Command '['gws', 'chat', 'spaces', 'list', '--params', '{"pageSize":1000}', '--page-all', '--page-limit', '50', '--format', 'json']' returned
non-zero exit status 1.
```

Test by running: `backupgoogle.py --config-dir /home/sanand/.config/gws-root.node@gmail.com/`

<!-- codex resume 019e4d4a-c55b-7002-b0d1-2cf0bd17cdee --yolo -->

## Generate script, 14 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

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
