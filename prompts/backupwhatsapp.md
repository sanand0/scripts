# backupwhatsapp.py

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
