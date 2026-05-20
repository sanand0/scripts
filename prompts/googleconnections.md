# googleconnections.py

## Initial script, 20 May 2026

<!--
cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly CLI script `googleconnections.py` that visits https://myaccount.google.com/connections using CDP 9222 and lists all apps that the user has connected their Google account to, along with the permissions granted to each app.

Sample output (in CSV format, if requested - default to TSV) - should be sorted by `url`:

```csv
url,app,time,permissions,id
https://claude.ai,Claude for Google Calendar,2026-02-21T03:33:00+0800,See your profile info;See and download any calendar you can access using your Google Calendar;View events on all your calendars,AcBx0o5_...
https://elevenlabs.io,ElevenLabs,2025-12-15T00:00:00+0800,See your profile info,AcBx0o5gg...
https://play.google.com/store/apps/details?id=com.anthropic.claude,2026-11-15T00:00:00+0800,See your profile info,AcBx0o7jJ...
...
```

Use the same format as I'm using here.

You will probably need to extract the IDs from the https://myaccount.google.com/connections page and visit these pages:

https://myaccount.google.com/connections/overview/$id - for the permissions
https://myaccount.google.com/connections/details/$id - for the url

Try doing this in multiple tabs in parallel for speed - without overloading the system.

Run and test. Verify that the output is correct and matches the summary stats on `https://myaccount.google.com/connections`.
Update README.md.

---

If you have saved output, save it in ./googleconnections.tsv.
If not, don't re-run.

<!-- codex resume 019e4453-82f7-7a21-a783-e087340e58b4 --yolo -->
