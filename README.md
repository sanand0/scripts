# Setup

These are personal productivity utilities that simplify my workflow on Windows (Cygwin) and Linux. These are in 2 places:

| Type    | Location                                         | Windows Path          | Linux Path            |
| ------- | ------------------------------------------------ | --------------------- | --------------------- |
| Public  | [GitHub](https://github.com/sanand0/scripts)     | `C:\code\scripts\`    | `~/code/scripts/`     |
| Private | [Dropbox](https://www.dropbox.com/home/scripts/) | `C:\Dropbox\scripts\` | `/c/Dropbox/scripts/` |

**Note**: I use `/c/Dropbox` as a symlink to `C:\Dropbox` in Cygwin to standardize scripts.

## Common Setup

```bash
echo 'source ~/code/scripts/setup.fish' >> ~/.config/fish/config.fish
echo 'source ~/code/scripts/setup.bash' >> ~/.bashrc
```

See [`ai-code-rules/`](ai-code-rules/README.md) for setting up AI code editors.

## Linux Setup

```bash
ln -s ~/code/scripts/.gitconfig ~/.gitconfig
ln -s ~/code/scripts/.tmux.conf ~/.tmux.conf
ln -s /c/Dropbox/scripts/.ssh ~/.ssh
chmod og-r .ssh/*
ln -s /c/Dropbox/scripts/llm.keys.json ~/.config/io.datasette.llm/keys.json
```

## Windows Setup

On an **Admin** command prompt, run:

```
CD /D C:\cygwin\home\Anand\
MKLINK /H .gitconfig C:\code\scripts\.gitconfig
MKLINK /D .ssh C:\Dropbox\scripts\.ssh
REM TODO: Set up `llm` keys.json on Windows
```

[Disable inherited permissions](https://stackoverflow.com/a/58275268/100904), remove all permissions,
and only add yourself with full permissions.

## System setup

Here are the setup details for my laptops.

- [Linux](setup/linux.md)
- [Windows](setup/windows.md)
- [Android](setup/android.md)
- [Online tools](setup/online.md) replacing installed software

# Scripts

- [chars](chars) lists non-ASCII characters in files.
- [git-uncommitted](git-uncommitted) lists directories not git-synced with remote
- [rgb](rgb) converts RGB to hex and vice versa.
- [viz.py](viz.py) embeds CSV files a HTML templates. This is the script that started [Gramener](http://gramener.com/) in 2011.
- [rofi-files.sh](rofi-files.sh) and [rofi-chrome-tabs.sh](rofi-chrome-tabs.sh) are used by rofi to get recent files.
- [generate/](generate/) has scripts to generate data.
- [daydream](daydream) fuses recalled concepts into radical ideas. Example: `daydream -c llm -c oblique-strategies "web app"`
- [recall](recall) shows a random note bullet. Example: `recall` or `recall talks`
- [ask](ask) records a short voice note, merges an optional `ask.md` system prompt, and sends it to `llm`.
- [gmail](gmail) offers a `typer`-based Gmail search CLI using OAuth tokens from `google_oauth.py`.
  - [google_oauth.py](google_oauth.py) refreshes and caches Google API tokens for the CLI utilities.
- [histfreq](histfreq) ranks the most common commands from a NUL-delimited shell history stream.
- [talkcode.sh](talkcode.sh) pipes spoken prompts through `ask`, generates code, and pastes it into the last active window.
- [unbrace.js](unbrace.js) unwraps single-statement JavaScript blocks.
- [update-files](update-files) caches directory listings so `rofi-files.sh` can stay fast even on large mounts.

## Services

`services/` has systemd services that are installed by [`services/setup.sh`](services/setup.sh). Current services are:

- `trending-repo-weekly.*`: Update trending GitHub repos
- `update-files-daily.*`: Update local files
- `update-files-weekly.*`: Update mounted files

## Tests

- `tests` stores regression checks
  - `test_gmail.py` verifies the Gmail CLI’s happy path.
