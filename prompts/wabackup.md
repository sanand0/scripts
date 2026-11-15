# wabackup

## Improve logging, 16 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

Update `wabackup` so that when it prints `Trying image 1/20: ${chat_name}` it also prints the date & time, and author/phone of the message for the image. That'll help me understand how old the image is.
Also, on the same line, add whether it succeeded or failed - and if it failed, when it will be retried (1 day, 2 days, etc.)
When printing chat summaries, currently it prints `Backing up ${chat_name}\n${chat_id} ${chat_file} ...`. Drop the `chat_file` (which reflects the chat name). Also, explain what the columns being printed are at the top.
While "Syncing wacli until idle..." stream its stdout and stderr.

--- <!-- steering -->

Note: don't stream from wacli if there's no terminal.

--- <!-- steering -->

If it's not a terminal, I don't want to see the wacli output at all.

---

Currently, it says "Images: 18 saved; 1289 waiting; 0 confirmed unavailable (skipped); 20 attempted." How do I get it to attempt more than 20?

---

Add an option to control the number of image attempts. Set the default limit to 100 instead of 20.

---

Update the time budget to 2 minutes.

<!-- codex resume 01a1e00a-cb75-7193-9847-59b389a46ea5 -->

## Use wacli, 13 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

`wacli` is available and working fine. Is it possible for `backupwhatsapp.py` to use it instead of CDP? What's the most efficient way to do this? I'm OK if we need to extend / modify the JSONL keys one-time in ~/Documents/data/whatsapp/*.jsonl to accommodate this, but I don't want to LOSE any information - including the image exports. Don't change `backupwhatsapp.py` but create a new `wabackup` that uses `wacli` instead of CDP and test it without disrupting the existing `backupwhatsapp.py` data or code. Make sure that the new script is robust and can be run in a similar way to `backupwhatsapp.py` - i.e. incremental backups, etc.

---

I ran wabackup --sync. There were several HTTP 403 / 410 responses and it ended with "RuntimeError: 1226 images pending; text saved. Rerun to retry; no archived images were removed."

~/Documents/data/whatsapp-wacli/ is much larger than whatsapp/ - is that because the image archive is more comprehensive? Or the data is more comprehensive? Or both? Is there any data in ~/Documents/data/whatsapp/ that's not in whatsapp-wacli/ that I would like to preserve? I plan to replace ~/Documents/data/whatsapp/ with ~/Documents/data/whatsapp-wacli/ (renaming them later) - so this will help me decide if I can just delete ~/Documents/data/whatsapp/ or if I need to merge some data from it into whatsapp-wacli/.

When I re-run wabackup --sync, will it try and fetch all the images than had a HTTP 403 / 410 response? Or will it skip them? Are some errors transient and therefore SHOULD be retried while others are permanent and therefore should be skipped? How can wabackup tell the difference? My preference is that it should retry transient errors but skip permanent errors. If it can't tell the difference, what's an effecient strategy to trade-off between completeness and speed?

What else should I consider before I delete ~/Documents/data/whatsapp/ and rename ~/Documents/data/whatsapp-wacli/ to ~/Documents/data/whatsapp/?

---

Rename ~/Documents/data/whatsapp/ to ~/Documents/data/whatsapp-old/ and rename ~/Documents/data/whatsapp-wacli/ to ~/Documents/data/whatsapp/.
Update the cache key, directory, etc. (if not already done) and any other changes to make sure that the next `wabackup` continues incrementally from the last run and uses the new ~/Documents/data/whatsapp/ directory as the default from now on.

Check if context.py needs any changes to accommodate this. If so, make the changes and test.

For the images, I want to make sure that:

- If there's something I can do to make the image downloadable (e.g. do something on the phone), it should be clearly documented when the script ends (e.g. "Open WhatsApp on your phone and scroll to these conversations and do these things:..." - written CLEARLY and SIMPLY.)
- If there's nothing I can do, the image should be skipped - e.g. phone confirms unavailable.
- If we're unsure, retry with increasing delays, e.g. skip for a day, then 2 days, then 4, etc. but that's just a suggestion. Think about what would be appropriate. Keep in mind that if I do what's needed on the phone, I might want to re-run the script immediately to get the images - and ideally, just running `wabackup` should be able to do this without me having to do anything else like specify a flag. Does that mean retry with increasing delays is not a good idea? Think about how I might realistically use it (blindly, most of the time, but sometimes looking at the output and acting on it) and what the best approach is for this.

Implement this approach and test.

---

Mentioning message ID when telling me what message image to download doesn't help as much as mentioning sender name and message text or something I can search for or see.
I would like to backup images from specific chats, one at a time. Mention how to do that in the 'To recover missing pictures:'

---

Archive backupwhatsapp.py the way I archive other things in this repo.
Schedule a run of wabackup every day as part of my daily run services - if a network is available. Even mobile network is fine for this.

---

No need for run_network_job - just run_job is enough. Any other simplifications or redundancies or unnecessary code / docs we can remove?

<!-- codex resume 01a1d24b-811d-74c3-87a7-fee7a24520af -->
