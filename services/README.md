# User Systemd Services

These units are installed by `./setup.sh` into the user systemd manager. The
setup script links units from this directory, reloads systemd, enables timers and
standalone services, and can run a health check.

## Services

- `activities-full-patch-weekly.*`: refreshes all patchable sources in every
  historical activity report on Sunday mornings. Daily runs patch only the
  latest seven reports, so older late-arriving data may take up to a week to
  appear.
- `daily-activities.*`: runs `daily-activities` every day around 1:15am. That
  service's wrapper runs:
  - A local refresh of the full and recent Rofi file indexes.
  - `activities.py`, which already refreshes/queries `browsing_history.py`.
  - `backupgoogle.py`, only on an unmetered connection.
  - `backupgoogle.py --config-dir /home/sanand/.config/gws-root.node@gmail.com`,
    only on an unmetered connection.
  - `backupgoogle.py --config-dir /home/sanand/.config/gws-anand@study.iitm.ac.in`,
    only on an unmetered connection.
  - `wabackup`, before the context rebuild (mobile/metered connections allowed).
  - `/home/sanand/code/summary.py`.
  - `summarize.py blog`.
  - `summarize.py transcript`.
  - `chatcli backup` and `claudecli backup`, publishing local ChatGPT and Claude captures before the context rebuild.
  - `rsync` backup to `hetzner:/home/`, only on an unmetered connection.
  - `rclone bisync` for `~/r2/files`, `~/r2/private`, and `~/r2/redirect`,
    only on an unmetered connection.
- `cli-proxy-api.service` runs the local model gateway via the mise shim.
- `trending-repo-weekly.*`: updates trending GitHub repos on Sunday mornings.
- `vlc-history.service`: follows VLC over MPRIS using `playerctl` and appends one
  row per played track to `~/Music/music-history.tsv` as
  `ISO-8601 timestamp<TAB>path-or-filename<TAB>tool` (`vlc`).
- `timer-failure-notify@.service`: records failure diagnostics for failed
  services.
- `servicestatus.*`: checks service status hourly, including a catch-up check
  after a missed hour. Fish displays unread alerts on the next prompt.
- `sync-plutonium.*`: hourly, one-way rsync of the entire
  `~/Documents/` on Graphene to `C:\Documents\` on Plutonium, and
  `~/r2/` to `C:\r2\`.
  It also archives the selected Codex, Claude, and Copilot history/settings under
  `C:\graphene\`, takes a consistent snapshot of Copilot's SQLite store, and
  copies the selected private code directories and environment files listed in
  `sync-plutonium.sh` under `C:\code\`.
  New and changed files are copied from Graphene; **Plutonium-only files are
  never deleted**. Windows-invalid names and case collisions are checked;
  colon-containing Documents filenames are copied with Windows-safe names.
  `SKIP_DIRS` excludes regenerable environments and caches (such as `.venv*`,
  `node_modules`, `__pycache__`, and `.wrangler`) from both validation and rsync.
  Symlinks to files within the selected trees are copied as files.
- `*.{service,timer}.disabled`: reference units that are intentionally not
  installed by `setup.sh`. This includes the retired
  `consolidate-transcripts-daily.*` units.

## Disabled Units

Renaming a unit with a `.disabled` suffix prevents `setup.sh` from installing
or enabling it. To remove a previously installed timer from the user systemd
manager after renaming its files, stop it and remove its stale links:

```bash
systemctl --user stop consolidate-transcripts-daily.timer
rm -f ~/.config/systemd/user/consolidate-transcripts-daily.{service,timer}
rm -f ~/.config/systemd/user/timers.target.wants/consolidate-transcripts-daily.timer
systemctl --user daemon-reload
```

To reactivate it, remove the `.disabled` suffixes from both files and run
`./setup.sh`.

## Install Or Check

Run from this directory:

```bash
./setup.sh
./setup.sh check
```

`setup.sh` refuses to overwrite non-symlink unit files under
`~/.config/systemd/user/`. If systemd is running an old copied unit, move that
file aside and re-run setup so the repo version is linked.
Setup also retires repo-managed links for the former `update-files-daily` units.

## Hourly Plutonium Sync

`./sync-plutonium.sh --dry-run` previews the Documents, r2, agent-history, and selected code syncs from Graphene to Plutonium via rsync/SSH on Tailscale.
Plutonium files are updated, but never deleted.

The systemd timer runs hourly after Graphene resumes or the user logs in.
Concurrent runs are prevented by `flock`.

Logs: `~/.cache/sanand-scripts/sync-plutonium/run.log`
Logs: `journalctl --user -u sync-plutonium.service`
Failure logs use the shared `timer-failure-notify@.service`.

Only unmetered connections are used by default (same as daily-activities);
set `SYNC_DOCUMENTS_ALLOW_METERED=1` for an intentional one-off override.

## VLC Playback History

`vlc-history.service` requires `playerctl` (Ubuntu: `sudo apt install -y playerctl`).
Install and start all repo-managed user units with `./setup.sh`, or just this one
after it has been linked:

```bash
systemctl --user enable --now vlc-history.service
systemctl --user status vlc-history.service
tail -f ~/Music/music-history.tsv
```

Pausing and resuming a track does not add another row. Stopping VLC (or a track)
resets the de-duplication state, so playing the same file again is logged again.

## CLIProxyAPI

The service uses the globally configured mise tool
(`mise use -g github:router-for-me/CLIProxyAPI`) and reads
`~/Dropbox/scripts/cli-proxy-api/config.yaml`. Keep the config private. The
proxy listens on `127.0.0.1:8317`, and credentials are stored separately in
`~/.cli-proxy-api/`. The unit starts with the user systemd session and skips
startup if the config or shim is missing. It retries unexpected exits after
10 seconds, including startup errors for which CLIProxyAPI exits successfully.

```bash
systemctl --user enable --now "$HOME/code/scripts/services/cli-proxy-api.service"
systemctl --user status cli-proxy-api.service
journalctl --user -u cli-proxy-api.service -f
```

To add a provider, run the shim interactively with the same config. For example:

```bash
"$HOME/.local/share/mise/shims/cli-proxy-api" \
  --config "$HOME/Dropbox/scripts/cli-proxy-api/config.yaml" --codex-login
```

Log in via:

```bash
cli-proxy-api --antigravity-login --config ~/Dropbox/scripts/cli-proxy-api/config.yaml
cli-proxy-api --codex-login       --config ~/Dropbox/scripts/cli-proxy-api/config.yaml
cli-proxy-api --copilot-login     --config ~/Dropbox/scripts/cli-proxy-api/config.yaml
# ... etc.
```

Use API key from `access.api-keys` and `http://127.0.0.1:8317/v1` as the OpenAI base URL.

```bash
curl http://127.0.0.1:8317/v1/models -H "Authorization: Bearer $(secret CLI_PROXY_API_KEY)"
```

After a mise upgrade, run `systemctl --user restart cli-proxy-api.service` to reload.
After editing the unit, run `systemctl --user daemon-reload` before restarting.

## Run manually

To refresh just the Rofi indexes, run `daily-activities --refresh-file-index`
or select **Refresh Rofi file index** in Rofi Commands.

```bash
# Reload if edited
systemctl --user daemon-reload

# Run once
systemctl --user start daily-activities.service

# Watch it run
journalctl --user -u daily-activities.service -f

# Check the result
systemctl --user status daily-activities.service
```

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

`servicestatus` (in the repo root) discovers new units and jobs automatically if
they follow these log conventions (see `daily-activities` and `sync-plutonium.sh`):

- Per job: `<ISO time> <tag>: start <job>: ...`, then `<ISO time> <tag>: ok <job> ...`,
  `<ISO time> <tag>: failed <job> exit=N ...`, or `<ISO time> <tag>: skip <job>: <reason>`.
  Print the job's own errors between `start` and its result. A successful job
  can emit `warning[<job>]: <message>` to surface a warning.
- Per run (optional): `END status=ok|failed|skipped` and `SKIP reason=<reason>`.
- Print a specific error line (`ERROR ...`, `error: ...`, an exception) - it is
  what `servicestatus` shows. Network/DNS/metered failures are shown as 🟡.

Check the next alert refresh with `systemctl --user list-timers servicestatus.timer`.
Refresh alerts immediately with `systemctl --user start servicestatus.service`.

Daily jobs should also be harmless to re-run. Prefer incremental updates,
merge-by-ID writes, skip-existing archive checks, and metadata fields that mark a
file as already processed.
