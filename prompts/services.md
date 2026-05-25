# services

## Handle errors, 21 May 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Go through the logs from `daily-activities` via `journalctl --user -u daily-activities.service`.
What errors did it face - especially today?
Is there an easy way to fix that error? If it's a simple fix with just a few lines of code change, go ahead. Else let me know and I'll decide whether to fix it now or later.

---

The problem may be that the network is not fully active as soon as my laptop wakes. A cleaner fix would be to wait for a minute after the laptop wakes before triggering the service - rather than gws retries.

<!-- codex resume 019e47b7-2f4d-7423-993c-eb0a9c3a7e77 -->

## Improve logging, 19 May 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

The logs emitted by the `daily-activities` scripts are too verbose. At least when run from inside `daily-activities`, don't log all skipped blogs, skipped transcript summaries, skipped meeting backups, etc.

Also, see how `gws` can suppress the `Using keyring backend: keyring` logs and implement them in the scripts that use `gws`.

Re-run the daily-activities service and check to ensure that the logs are genuinely useful and not too verbose.

## Update backup scripts, 19 May 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Append the following sync commands to `daily-activities`:

```bash
export _RCLONE_BISYNC_OPTIONS='--create-empty-src-dirs --slow-hash-sync-only --fast-list --size-only --checkers 16 --transfers 8 --resilient --metadata --fix-case --exclude "**/node_modules/**" --exclude "**/__pycache__/**" --exclude "**/localdata/**" --verbose --progress'

rsync -avzP \
  ~/Documents/audio \
  ~/Documents/bcg \
  ~/Documents/books \
  ~/Documents/calls \
  ~/Documents/comics \
  ~/Documents/data \
  ~/Documents/gitlab \
  ~/Documents/infy \
  ~/Documents/linkedin \
  ~/Documents/screenplays \
  ~/Documents/talks \
  ~/Pictures \
  hetzner:/home/
rclone bisync ~/r2/files r2:files $_RCLONE_BISYNC_OPTIONS
rclone bisync ~/r2/private r2:private $_RCLONE_BISYNC_OPTIONS
rclone bisync ~/r2/redirect r2:redirect $_RCLONE_BISYNC_OPTIONS
```

These currently work only if the right configurations are exposed in the environment. Make sure they are exposed.

Ensure that these scripts, as well as any other scripts currently in `daily-activities` that requires a lot of bandwidth, are only run when on an unmetered connection.

Run and test in the services environment. Make sure that failures do not prevent the rest of the scripts from running, and errors are logged in an intuitive way.

Update docs, setup, etc.

---

Go ahead and run the real systemd job as a test.

<!-- codex resume 019e3e15-fa03-7fb1-9afa-d9b3875c9db9 -->

## Add daily services and docs, 19 May 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Add a `daily-activities` shell script that runs the following scripts:

/home/sanand/code/scripts/activities.py (which effectively runs browsing_history.py, so we don't need to run that again - just document this)
/home/sanand/code/scripts/backgoogle.py
/home/sanand/code/scripts/backupmeet.py
/home/sanand/code/summary.py

... and add a `services/daily-activities.{service,timer}` that runs it every day at a reasonable time.

Make sure that errors or unexpected situations are logged, but the failure of one script should not prevent the others from running.

See `services/consolidate-transcripts-daily.{service,timer}`, etc. to understand how Python scripts are run from systemd services. Remember that the environment you run in may be very different from the user's systemd services environment (env variables, paths, permissions, etc.)

Add a services/README.md documenting the services I have set up, how to check logs, how to set troubleshoot, how to set up new timers and services, what to watch out for, etc. See ~/code/infra/timers/ for related documentation.

Run and test.

---

Add these two additional commands to daily-activities:

```bash
summarize.py blog
summarize.py transcript
```

... and update relevant docs, setup, etc. Test it.

---

Check two things:

1. When run in a services context, will all the scripts pick up the API keys and any other environment variables from /home/sanand/code/scripts/.env?
2. Is it harmless to re-run `daily-activities`? That is, a second run would merely update things incrementally and it can be re-run multiple times?

If not, modify the scripts minimally to do so. Then run run the full daily wrapper, ideally in a services context, and check that it works end to end.

---

Modify backupmeet.py to log in a more intuitive way consistent with the others. Re-run and test.

<!-- codex resume 019e3daa-ae80-7a01-96ed-a47a87791be8 -->
