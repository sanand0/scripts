# Linux

Here is the setup for my Linux laptops.

## Graphene, 20 Mar 2025

[Lenovo ThinkPad X11](https://pcsupport.lenovo.com/sg/en/products/laptops-and-netbooks/thinkpad-p-series-laptops/thinkpad-p15s-gen-2-type-20w6-20w7/20w7/20w7s0gd00/pf2t55qf) running Ubuntu 24.04 LTS.

- Create a user `sanand`
- Install Dropbox: https://www.dropbox.com/install-linux
- Install Edge: https://www.microsoft.com/en-us/edge/business/download (Scroll down to "Looking for an older version of Edge?"). Set as default browser
- Install VS Code: https://snapcraft.io/code
  - `xdg-mime default code.desktop text/markdown` or right-click in Nautilus and select "Open with ..." to set the binding
- Install Cursor: https://dev.to/mhbaando/how-to-install-cursor-the-ai-editor-on-linux-41dm (also https://gist.github.com/evgenyneu/5c5c37ca68886bf1bea38026f60603b6)
  - [Copy VS Code profile](https://github.com/getcursor/cursor/issues/876#issuecomment-2099147066)
  - In Preferences > Open Keyboard Shortcuts, change "Add Cursor Above" to Ctrl+Alt+UpArrow and "Add Cursor Below" to Ctrl+Alt+DownArrow
  - To update cursor, [download](https://www.cursor.com/downloads), shut down cursor, replace image at `/opt/cursor.appimage`, and restart cursor
- Software
  - git: `sudo apt install git git-lfs`
  - System Python: `sudo apt install python3 python3-pip` since some tools _require_ a system python. Maybe fnm?
  - curl: `sudo apt install curl`
  - fish: `sudo apt install fish; printf "/usr/bin/fish\n" | sudo tee -a /etc/shells;`
  - uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - fnm: `curl -fsSL https://fnm.vercel.app/install | bash` to install node
  - node: `fnm install 23`
  - deno: `curl -fsSL https://deno.land/install.sh | sh` - which auto-installed to `~/.deno/bin/deno` and configured `~/.config/fish/conf.d/deno.fish` and `~/.bashrc`
  - autokey: `sudo apt install autokey-gtk` and set up with phrases
  - rclone: `curl https://rclone.org/install.sh | sudo bash` - mounts hetzner storage box on startup
  - caddy: `sudo apt install caddy`
  - fd: `sudo apt install fd-find && sudo ln -s /usr/bin/fdfind /usr/local/bin/fd` for fast file searches
  - jq: `sudo apt-get install jq`
  - tmux: `sudo snap install tmux`
  - fdupes: `sudo apt install fdupes` to find duplicate files
  - rofi: `sudo apt install rofi` to switch windows.
    - Modify `/usr/share/applications/microsoft-edge.desktop` to add a remote debugging port as `Exec=/usr/bin/microsoft-edge-stable --remote-debugging-port=9222 %U`
    - `rofi-theme-selector` - pick Monokai, android_notification, or gruvbox-hard-dark
    - In `~/.config/rofi/config.rasi`, add `window { height: 80%; }`
  - llm: `mkdir -p ~/apps/llm; cd ~/apps/llm; uv venv; uv pip install llm`
    - `llm install llm-cmd llm-openrouter`
    - `llm models default openrouter/deepseek/deepseek-chat-v3-0324:free` or `llm models default openrouter/google/gemini-2.5-pro-exp-03-25:free`
  - openwebui: `mkdir -p ~/apps/openwebui; cd ~/apps/openwebui; uv venv --python 3.11; uv pip install open-webui`
  - pandoc: [Download](https://github.com/jgm/pandoc/releases) and `sudo dpkg -i ...`
  - FiraCode Nerd Font: `mkdir -p ~/.local/share/fonts && curl -L https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FiraCode.tar.xz -o ~/.local/share/fonts/FiraCode.tar.xz && tar -xf ~/.local/share/fonts/FiraCode.tar.xz -C ~/.local/share/fonts && fc-cache -fv ~/.local/share/fonts`
  - [fzf](https://github.com/junegunn/fzf) ([video](https://youtu.be/F8dgIPYjvH8)) instead of Everything: `mkdir -p ~/.local/bin && curl -L https://github.com/junegunn/fzf/releases/download/v0.60.3/fzf-0.60.3-linux_amd64.tar.gz | tar xz -C ~/.local/bin/`.
    - Just press `Ctrl+T` to open fzf when typing a command.
  - bat: `sudo apt install bat && sudo ln -s /usr/bin/batcat /usr/local/bin/bat` for color previews in fzf
  - [Starship](https://starship.rs/) fast prompt: `curl -sS https://starship.rs/install.sh | sh`
  - [zoxide](https://github.com/ajeetdsouza/zoxide) smart cd (`z`): `curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh`
    - More modern than autojump, fasd, etc.
  - ImageMagick:
    - `wget https://imagemagick.org/archive/binaries/magick`
    - `sudo mv magick /usr/local/bin/magick`
    - `sudo chmod +x /usr/local/bin/magick`
  - xclip instead of clip: `sudo apt install xclip`
  - gh cli:
    - `curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg`
    - `echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null`
    - `sudo apt install gh`
  - glab cli:
    - `curl -LO https://gitlab.com/gitlab-org/cli/-/releases/v1.55.0/downloads/glab_1.55.0_linux_amd64.deb`
    - `sudo apt install ./glab_1.55.0_linux_amd64.deb`
    - `glab config set -g host code.gramener.com`
  - Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
    - `sudo apt install nvidia-modprobe`
    - `sudo nvidia-modprobe -u`
    - `sudo service ollama restart`
    - `ollama pull gemma3`
    - `ollama pull phi4-mini`
  - Audacity via "Software"
  - [TouchEgg](https://github.com/JoseExposito/touchegg) for touch gestures
    - `sudo add-apt-repository ppa:touchegg/stable; sudo apt update; sudo apt install touchegg`
  - Flatpak: `sudo apt install flatpak`
    - `sudo apt install gnome-software-plugin-flatpak`
    - `flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
    - [Meld](https://flathub.org/apps/org.gnome.meld) instead of Beyond Compare
    - [Touche](https://github.com/JoseExposito/touche)
      - Swipe with 3 fingers - Up: Execute a command `amixer sset Master 5%+`. Repeat command. (Pulse is not installed)
      - Swipe with 3 fingers - Down: Execute a command `amixer sset Master 5%-`. Repeat command.
      - Swipe left/right with 3 fingers: `dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause` on Gesture start.
  - Peek instead of ScreenToGIF: `sudo apt install peek`
  - [Warp](https://www.warp.dev/) by downloading and `sudo dpkg -i ...`
  - Docker (via CLI installation instructions)
  - Foliate: via "App Center"
    - User stylesheet at `~/snap/foliate/current/.config/com.github.johnfactotum.Foliate/user-stylesheet.css` has `p { line-height: 1.8 !important; }`
  - Beekeeper Studio instead of SQLiteStudio: Installed via app store
  - 7zip, Zoom, OBS
- Configurations
  - Settings > Keyboard > Custom Shortcuts > Add:
    - `Alt+E` runs `nautilus`
    - `Alt+F1` runs `rofi -show-icons -show combi -modes combi -combi-modes "window,tab:/home/sanand/code/scripts/rofi-chrome-tabs.sh,file:/home/sanand/code/scripts/rofi-files.sh"`
  - `sudo apt install gnome-tweaks`
    - [Focus follows mouse](https://askubuntu.com/a/978404/601330)
  - `sudo apt gnome-shell-extension-manager` and then run Extension Manager to install
    - [dash-to-panel](https://github.com/home-sweet-gnome/dash-to-panel)
    - Clipboard History - Win+Shift+V
    - Emoji Copy - Win+.
  - Set up hetzner storage box on rclone and mount: `mkdir -p ~/hetzner && rclone mount hetzner:/ /home/sanand/hetzner --vfs-cache-mode full --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon`
  - Set up dropbox on rclone but don't mount it
  - Disable sudo password: `echo "$USER ALL=(ALL:ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$USER`
  - Disable Ctrl+Alt+Arrow keys: `gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-up "['']" && gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-down "['']"` [Ref](https://unix.stackexchange.com/a/673065)
  - Settings > Apps > Default Apps > Web > Microsoft Edge
  - Settings > System > Formats > United Kingdom
  - Settings > Privacy and Security > Screen Lock > Automatic Screen Lock > False
  - Settings > Privacy and Security > Screen Lock > Screen Lock on Suspend > False
  - SSH setup: `cd ~/.ssh; ln -s ~/Dropbox/.ssh; chmod og-r .ssh/*`
  - Don't enable Wayland since touchegg gestures works better with X11 but if you _do_ want to enableWayland, set `sudo sed -i 's/#WaylandEnable=false/WaylandEnable=true/' /etc/gdm3/custom.conf; sudo systemctl restart gdm3` [Ref](https://askubuntu.com/a/1258280/601330) [Usage](https://help.ubuntu.com/lts/ubuntu-help/touchscreen-gestures.html)
  - #TODO: Always on top
  - #TODO: CLI for alarm
  - #TODO: 4-finger swipe = drag
- Notes
  - `xrandr --output eDP-1 --brightness 0.5 --gamma 0.9` sets the SOFTWARE brightness and gamma.
  - Connecting to the Hyderabad airport wifi failed. I set the Identity > Mac Address to the default and Cloned Address to Random.
  - Shortcuts:
    - Fn+L = Low power mode. Fn+M = Medium power mode. Fn+H = High power mode.
    - Fn+S = Screenshot. PrtSc = Screenshot area.
    - Fn+4 = Sleep mode.

Things I skipped:

- [Atuin](https://docs.atuin.sh/guide/installation/): `curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh`. It interferes with VS Code's terminal sticky scroll, and not _that_ useful.
- Warp terminal app. I prefer `llm cmd` for simplicity.
- Guake: Visor terminal. Ctrl+F12. Visor appears, which is a shell.

Notes:

- Use `fish_trace=1 fish` to debug fish startup or fish scripts.
