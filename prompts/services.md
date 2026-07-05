# services

## Capture browser tabs, 05 Jul 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Update `daily-activities` to run the equivalent of:

`uv run ~/code/scripts/edge_tabs.py --json | jaq -c '.timestamp as $t | .windows[] | .id as $w | .tabs[] | {timestamp:$t, window:$w, title, url}' > ~/Documents/data/browser-tabs/$(date +%F).jsonl`

Make sure paths work fine, even when run from a systemd service context. Test it.
This can run even without an Internet connection.
This is fairly fast. It can run right after `activities.py`.

---

Write to ~/Documents/data/open-tabs/ instead of browser-tabs. Rename existing directory. Rename variables / functions / ... if required. Update README.md.

<!-- codex resume 019f322a-3e1d-7de3-93e2-4c9a6dae9894 -->

## Archive unused, 07 Jun 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

I no longer need the services/consolidate-transcripts-daily service/timer. Minimally disable it - maybe moving it into a services/archive/ directory - or is there a better way, maybe just marking it disabled? Update services/README.md accordingly.

<!-- codex resume 019ea0d5-c489-7283-9d76-db0e34f9c53d -->

## Speed up, 06 Jun 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

`services/daily-activities.service` takes a long time and has an initial preloading step that takes a long time. Maybe others. Review the logs, see what are the steps that take the longest time, and suggest the top 5 fixes that have the highest time reduction impact with the least effort and functional impact.

List these for me to review. Help me pick by sharing the extent of the change (e.g. LOC, simple/complex) and impact (risks) of the change

---

Implement #1 and #3. Run and test.

<!-- codex resume 019e9b99-7036-7772-ae94-44f3dc23ccf9 -->

## Back up personal GMail, 31 May 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

`daily-activities` runs backupgoogle.py. This backs up my email from s.anand@gramener.com.
Add another activity to run it with `--config-dir` as `/home/sanand/.config/gws-root.node@gmail.com` so that it'll back up my personal email as well.

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
