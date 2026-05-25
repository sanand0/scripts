# User Systemd Services

These units are installed by `./setup.sh` into the user systemd manager. The
setup script links units from this directory, reloads systemd, enables timers,
and can run a health check.

## Services

- `consolidate-transcripts-daily.*`: runs `consolidate_transcripts.py` from the
  transcripts notes directory every day around 12:05am.
- `daily-activities.*`: runs `daily-activities` every day around 1:15am. That
  service waits 60 seconds before the wrapper starts, so catch-up runs after
  wake have a little time for network setup. The wrapper runs:
  - `activities.py`, which already refreshes/queries `browsing_history.py`.
  - `backupgoogle.py`, only on an unmetered connection.
  - `backupmeet.py --yes`, only on an unmetered connection.
  - `/home/sanand/code/summary.py`.
  - `summarize.py blog`.
  - `summarize.py transcript`.
  - `rsync` backup to `hetzner:/home/`, only on an unmetered connection.
  - `rclone bisync` for `~/r2/files`, `~/r2/private`, and `~/r2/redirect`,
    only on an unmetered connection.
- `update-files-daily.*`: refreshes the local file index every day around
  12:30am.
- `trending-repo-weekly.*`: updates trending GitHub repos on Sunday mornings.
- `timer-failure-notify@.service`: records failure diagnostics for failed
  services.
- `*.service.disabled`: reference units that are intentionally not installed by
  `setup.sh`.

## Install Or Check

Run from this directory:

```bash
./setup.sh
./setup.sh check
```

`setup.sh` refuses to overwrite non-symlink unit files under
`~/.config/systemd/user/`. If systemd is running an old copied unit, move that
file aside and re-run setup so the repo version is linked.

## Logs

Check timer state:

```bash
systemctl --user list-timers --all
systemctl --user status daily-activities.timer daily-activities.service
systemctl --user --failed
```

Read logs:

```bash
journalctl --user -u daily-activities.service --since today --no-pager
journalctl --user -u daily-activities.service --since "1 week ago" --no-pager
journalctl --user --since "1 week ago" -g "Failed|failed|error|Error|warning|Warning" --no-pager
```

Failure notifications are written under:

```bash
~/.cache/sanand-scripts/timer-failures/
```

## Troubleshooting

User systemd services do not run in the same environment as an interactive
terminal. Expect a different `PATH`, current directory, shell profile state,
environment variables, OAuth token visibility, mounted drives, and network
availability.

`daily-activities` explicitly exports variables from
`/home/sanand/code/scripts/.env` before it starts child scripts, so API keys are
available even though the service working directory is `/home/sanand`.

The wrapper also sets `XDG_CONFIG_HOME=/home/sanand/.config` and
`RCLONE_CONFIG=/home/sanand/.config/rclone/rclone.conf`, and tries common
user-session SSH agent sockets if `SSH_AUTH_SOCK` was not imported. The Hetzner
backup still depends on the `hetzner` host entry and SSH key under
`/home/sanand/.ssh/`. The R2 jobs depend on the `r2` remote in the rclone config.

Bandwidth-heavy jobs are guarded by NetworkManager's metered flag via `nmcli`.
If no connected Wi-Fi/Ethernet device is clearly unmetered, those jobs are
skipped and logged. For a deliberate one-off override, run with
`DAILY_ACTIVITIES_ALLOW_METERED=1`.

Prefer absolute paths in `ExecStart`. If a Python script depends on PEP 723
metadata or a managed environment, run it via `/home/sanand/.local/bin/uv run`
as the existing units do. Put required `PATH` entries in the unit, not in
`.bashrc` or `.profile`.

Include `/home/sanand/.local/share/mise/shims` when a service needs tools such
as `gws` that are exposed by mise shims.

For Google Workspace jobs, verify auth from a similar environment before
debugging application logic:

```bash
env -i HOME="$HOME" PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/bin:/home/sanand/.local/bin:/home/sanand/.local/share/mise/shims:/home/sanand/bin" gws auth status
```

For daily sync prerequisites, check the rclone remote and the Hetzner SSH alias:

```bash
rclone lsd r2:
ssh -G hetzner | head
```

If a timer says it ran but nothing happened, check the service logs first. If a
timer never triggers, run `systemctl --user daemon-reload`, then `systemctl
--user enable --now UNIT.timer`, then inspect `systemctl --user list-timers
--all`.

## Adding A Timer

1. Add a `name.service` with `Type=oneshot`, absolute `ExecStart`, a stable
   `WorkingDirectory`, an explicit `Environment=PATH=...`, and
   `OnFailure=timer-failure-notify@%n.service`.
2. Add a matching `name.timer` with a concrete `OnCalendar=*-*-* HH:MM`,
   `Persistent=true`, `AccuracySec=...`, `RandomizedDelaySec=...`, and
   `WantedBy=timers.target`.
3. Stagger daily timers instead of using generic `OnCalendar=daily`.
4. Make scripts idempotent and safe to catch up after sleep or travel.
5. Run `./setup.sh`, `./setup.sh check`, and inspect recent logs.

For wrappers that run multiple jobs, log start/end/exit status for each job,
continue after failures, and exit non-zero at the end if any job failed so
systemd can record and notify the aggregate failure.

Daily jobs should also be harmless to re-run. Prefer incremental updates,
merge-by-ID writes, skip-existing archive checks, and metadata fields that mark a
file as already processed.
