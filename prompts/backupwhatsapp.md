# backupwhatsapp.py

## Optimization, 29 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/tools/whatsappscraper:/home/sanand/code/tools/whatsappscraper:ro -v /home/sanand/Documents/data/whatsapp:/home/sanand/Documents/data/whatsapp
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

`backupwhatsapp.py` needs two improvements:

1. It scans too far back in the past, which is unnecessary. For example, I've been running it daily, and yet when I ran it today, it scanned conversations all the way back to "bbdaily" which was last updated on 13 Mar 2026. Today is 29 May 2026. Conversation dates are visible ("Yesterday", "Wednesday", "13/03/2026", etc.) It should make a reasonable judgement (with buffer) that a conversation that's WELL before the last updated conversation need not be scanned unless the options explicitly say so. When running `backupwhatsapp.py` without options, this should be the default behavior. This will make it much faster to run every one or three days.
2. It scrolls the conversation list every time from the start even when the conversation list shows the next conversation to be scanned. When scanning the previous conversation, it has already scrolled to a certain point, and the next conversation, very likely, is visible just below that. Modify it so that it checks if scrolling is required before scrolling there.

Read `prompts/backupwhatsapp.md` for how the prompting has evolved - it might help.

Run and test.

---

Why is 14 days a good default buffer? Based on the "inter-conversation duration" distribution, what do you infer and can this be limited to about 4 conversations with a 95% confidence?

---

Go ahead, change the current from 14 to 3 and lower INCREMENTAL_SORT_SAFETY from 6 to 4.

## Reconciliation, 25 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/tools/whatsappscraper:/home/sanand/code/tools/whatsappscraper:ro -v /home/sanand/Documents/data/whatsapp:/home/sanand/Documents/data/whatsapp
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

I ran `backupwhatsapp.py` and it updated several chats - see `/home/sanand/Documents/data/whatsapp/changes-2026-05-25.md` for the list.

I'm entirely sure that barring the first few (not sure how many) conversations, the rest were NOT updated, i.e. the script says there are changes but there couldn't have been. It's also notable that the changed and seen values are the same. I suspect that it's because something changed in the DOM.

I pressed Ctrl+C near 56/97 - so the conversations up to that would have been updated but not those after that, I think. So you might have a record of some conversations with the old content vs new content.

Go through it. Find out what's changed. (It's been a few hours since I last ran, so there may be some new conversations that have come up. These would likely be near the top.)

Modify the script so that, if there are DOM changes (or even otherwise), I don't lose information. This is important. I don't want newer scripts ERASING or reducing information I've already collected. Maybe some kind of history / versioning that's lightweight? Think about what's the cleanest way to do it keeping in mind that AI agents will be running `grep` on these files and we want them to be token-friendly.

If there are any other ways to make it more robust, do so

<!-- codex resume 019e5d55-7466-7b60-bee3-d7aaa063673a --yolo -->

## Efficiency, 19 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/tools/whatsappscraper:/home/sanand/code/tools/whatsappscraper:ro -v /home/sanand/Documents/data/whatsapp:/home/sanand/Documents/data/whatsapp
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify backupwhatsapp.py to ensure that:

- When I update first thing in the morning, the conversation list shows "Yesterday" as the last updated time, not the actual time. That triggers unnecessary scanning of conversations and messages. Check if there is a smarter way to do this. For example, checking for unread messages as a signal, checking if conversation lists are sorted by time in which case we can skip starting from the first conversation that has no new content (or going down a few further to be safe). Of course, to do this, you need to verify if the conversations are, in fact, reliably sorted, and plant a diagnostic in the script to report if that's not the case in the future - letting me know to revise the script revisiting this assumption.
- If I go to a different time zone (Singapore, India, Europe, US, ...) the timing detection still works - especially from the conversation list

Run and test.

<!-- codex resume 019e3e1c-ceaa-7573-8c06-dd9839d21655 --yolo -->

## Tweaks, 17 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/tools/whatsappscraper:/home/sanand/code/tools/whatsappscraper:ro -v /home/sanand/Documents/data/whatsapp:/home/sanand/Documents/data/whatsapp
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify backupwhatsapp.py to ensure that:

- the modified time of any file it writes matches the latest message timestamp
- it doesn't perform unnecessary scans. For example, if based on the last message timestamp in the list of conversations, it can determine that there are no conversations with new messages since the last backup, it should skip scanning conversations and messages altogether.

Update the timestamps of all JSON files.
Run and test.

---

Run again. This time, since you just ran backupwhatsapp.py a short while ago, it should only need to scan a few conversations, say 1-2, since the last update and nothing else, and should exit quickly.

If it doesn't, see why not and fix it.

<!-- codex resume 019e359a-be39-7f23-9841-5061d4cc6270 --yolo -->

## Write bulk scraper, 17 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/tools/whatsappscraper:/home/sanand/code/tools/whatsappscraper:ro -v /home/sanand/Documents/data/whatsapp:/home/sanand/Documents/data/whatsapp
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly bulk scraper script `backupwhatsapp.py`, that goes through my WhatsApp conversations via CDP 9222 and backs up my WhatsApp conversations.

The conversations should be saved in `~/Documents/data/whatsapp/*.jsonl` where each conversation is a separate JSONL file with the file name same as the conversation title. Go through the last time when the conversation was updated and only back up conversations that have been updated since the last backup. Then go to the next conversation and continue until interrupted or all conversations (since the last run) are backed up. Allow the user to pick specific conversations to back up on the CLI, or pick a start / end date range. But in every case, treat `~/Documents/data/whatsapp/*.jsonl` as a database to be updated and maintained rather than overwritten.

See /home/sanand/code/tools/whatsappscraper and ./backup\*.py for a better understanding.

---

Run backupwhatsapp.py.

Start by having it back up all conversations whose latest message is today, and is able to back up the conversation at least as far back as the beginning of the year or the last 100 messages, whichever is shorter.

Check if the output is OK. I reloaded WhatsApp - maybe classes have changed? Double-check everything.

---

/compact

---

Now do a full run to back up all conversations since 1 Jan 2026. It's OK to grant an exception for "The GenerativeAI Group" or any other group that just do not scroll up before a certain point in time, e.g. by saying "Use WhatsApp on your phone to see older messages..." but otherwise, try and back up the complete list.

If you need to modify the program for better observability or control, feel free to do so. If you want to run it in batches, feel free to do so.

Keep in mind that group / conversation / people names may change. Modify the file name to include an immutable ID that you can use to locate the file in the future.

My aim is that the next time I run backupwhatsapp.py, it should do an incremental backup, i.e. capture every new message since the last update of every conversation, and add it to the existing JSONL files in place without creating duplicates. Make sure this will happen.

<!-- codex resume 019e33ab-647b-71b1-ae31-30ec3a4d8b8b --yolo -->
