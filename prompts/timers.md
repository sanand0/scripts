# Prompts

## Initial draft, 09 Jun 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Create a simple, minimal `timers` shell script, fzf-based, that lists all systemd user timers (e.g. via `systemctl --user list-timers --all`, maybe with --output=json). This should show all the timers along with when ran last and when they'll run next, sorted by the most recently run timer first. For example:

```
update-files-daily.timer ran 10min ago (9 Jun 2026, 6:30 am IST). Next: in 17h (10 Jun 2026, 12:31 am IST).
...
```

Selecting any timer should run `journalctl --user -u ${timer_name}.service --since "3 days ago" --lines=all --follow`

<!-- codex resume 019ea9f2-85fb-7e90-bd52-9d119db52ce2 -->
