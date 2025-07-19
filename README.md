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

Add [`ai-code-rules.md`](ai-code-rules.md) to VS code's `github.copilot.chat.codeGeneration.instructions` or Cursor or other AI code editor settings.

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
