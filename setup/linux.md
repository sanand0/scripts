# Linux

Here is the setup for my Linux laptops.

## Graphene, 20 Mar 2025

[Lenovo ThinkPad X11](https://pcsupport.lenovo.com/sg/en/products/laptops-and-netbooks/thinkpad-p-series-laptops/thinkpad-p15s-gen-2-type-20w6-20w7/20w7/20w7s0gd00/pf2t55qf) running Ubuntu 24.04 LTS.

- Create a user `sanand`
- Install Dropbox: https://www.dropbox.com/install-linux
- Install Edge: https://www.microsoft.com/en-us/edge/business/download (Scroll down to "Looking for an older version of Edge?"). Set as default browser
  - Enable Copilot. Download [HubApps.txt](https://github.com/NixOS/nixpkgs/issues/345125#issuecomment-2440433714) and copy it to `~/.config/microsoft-edge/Default/HubApps`
- Add Edge startup options: remote debugging. [Persist changes](https://chatgpt.com/share/68528565-0d34-800c-b9ec-6dccca01c24c)
  ```bash
  mkdir -p ~/.local/share/applications
  desktop-file-install --dir=$HOME/.local/share/applications /usr/share/applications/microsoft-edge.desktop \
    --set-key=Exec \
      # For Wayland, add --enable-features=UseOzonePlatform --ozone-platform=wayland
    --set-value='/usr/bin/microsoft-edge-stable --remote-debugging-port=9222 %U'
  update-desktop-database ~/.local/share/applications   # refresh caches
  ```
- Install VS Code: https://snapcraft.io/code
  - `xdg-mime default code.desktop text/markdown` or right-click in Nautilus and select "Open with ..." to set the binding
  - Set GitHub Copilot code generation instructions to [ai-code-rules.md](ai-code-rules.md): `"github.copilot.chat.codeGeneration.instructions": [{"file": "/home/sanand/code/scripts/ai-code-rules.md"}]`
- Install Cursor: https://dev.to/mhbaando/how-to-install-cursor-the-ai-editor-on-linux-41dm (also https://gist.github.com/evgenyneu/5c5c37ca68886bf1bea38026f60603b6)
  - [Copy VS Code profile](https://github.com/getcursor/cursor/issues/876#issuecomment-2099147066)
  - In Preferences > Open Keyboard Shortcuts, change "Add Cursor Above" to Ctrl+Alt+UpArrow and "Add Cursor Below" to Ctrl+Alt+DownArrow
  - To update cursor, [download](https://www.cursor.com/downloads), shut down cursor, replace image at `/opt/cursor.appimage`, and restart cursor
- Install [Windsurf](https://windsurf.com/editor/download-linux)
- Software
  - Opera: From https://www.opera.com/download
  - git: `sudo apt install git git-lfs`
  - System Python: `sudo apt install python3 python3-pip` since some tools _require_ a system python. Maybe fnm?
  - curl: `sudo apt install curl`
  - micro: `cd ~/.local/bin; curl https://getmic.ro | bash`
  - fish: `sudo apt install fish; printf "/usr/bin/fish\n" | sudo tee -a /etc/shells;`
  - uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - fnm: `curl -fsSL https://fnm.vercel.app/install | bash`
  - node: `fnm install 23`
  - deno: `curl -fsSL https://deno.land/install.sh | sh` - which auto-installed to `~/.deno/bin/deno` and configured `~/.config/fish/conf.d/deno.fish` and `~/.bashrc`
  - duckdb: `curl https://install.duckdb.org | sh` (re-run to upgrade)
  - sqlite3: `sudo apt install sqlite3`
  - caddy: `sudo apt install caddy`
  - fd: `sudo apt install fd-find && sudo ln -s /usr/bin/fdfind /usr/local/bin/fd` for fast file searches
  - jq: `sudo apt install jq`
  - csvkit: `sudo apt install csvkit`
  - csvq: `curl -L https://github.com/mithrandie/csvq/releases/download/v1.18.1/csvq-v1.18.1-linux-amd64.tar.gz | tar xzO csvq-v1.18.1-linux-amd64/csvq > ~/.local/bin/csvq && chmod +x ~/.local/bin/csvq`
  - tmux: `sudo snap install tmux`
  - ffmpeg: `sudo apt install ffmpeg`
  - lynx: `sudo apt install lynx`
  - w3m: `sudo apt install w3m`
  - neomutt: `sudo apt install neomutt`
  - glow: `sudo snap install glow` - Markdown rich text formatter
  - ngrok: `sudo snap install ngrok`
  - fdupes: `sudo apt install fdupes` to find duplicate files
  - rclone: `curl https://rclone.org/install.sh | sudo bash` - mounts hetzner storage box on startup
  - gcloud: `curl https://sdk.cloud.google.com | bash`
  - opentofu: `sudo snap install --classic opentofu` - Terraform alternative
  - aws: `sudo snap install --classic aws`
  - psql: `sudo apt-get install -y postgresql-client`
  - autokey: `sudo apt install autokey-gtk` and set up with phrases. But there's no [Wayland support](https://github.com/autokey/autokey/issues/87)
    - expanso: Needs libwxbase which is no longer installed with Debian?
  - rofi: `sudo apt install rofi` to switch windows.
    - `rofi-theme-selector` - pick Monokai, android_notification, or gruvbox-hard-dark
    - In `~/.config/rofi/config.rasi`, add `window { height: 80%; }`
  - ttyd: `sudo snap install ttyd --classic` to expose terminal on the web
  - pandoc: [Download](https://github.com/jgm/pandoc/releases) and `sudo dpkg -i ...`
  - supabase: [Download](https://github.com/supabase/cli/releases) and `sudo dpkg -i ...`
  - f2: [Download](https://github.com/ayoisaiah/f2/releases) and `sudo dpkg -i ...`
  - ripgrep: [Download](https://github.com/BurntSushi/ripgrep/releases) and `sudo dpkg -i ...`
  - FiraCode Nerd Font: `mkdir -p ~/.local/share/fonts && curl -L https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FiraCode.tar.xz -o ~/.local/share/fonts/FiraCode.tar.xz && tar -xf ~/.local/share/fonts/FiraCode.tar.xz -C ~/.local/share/fonts && fc-cache -fv ~/.local/share/fonts`
  - [fzf](https://github.com/junegunn/fzf) ([video](https://youtu.be/F8dgIPYjvH8)) instead of Everything: `mkdir -p ~/.local/bin && curl -L https://github.com/junegunn/fzf/releases/download/v0.60.3/fzf-0.60.3-linux_amd64.tar.gz | tar xz -C ~/.local/bin/`.
    - Just press `Ctrl+T` to open fzf when typing a command.
  - bat: `sudo apt install bat && sudo ln -s /usr/bin/batcat /usr/local/bin/bat` for color previews in fzf
  - wireguard (VPN): `sudo apt install -y wireguard-tools`
  - [Starship](https://starship.rs/) fast prompt: `curl -sS https://starship.rs/install.sh | sh`
  - [zoxide](https://github.com/ajeetdsouza/zoxide) smart cd (`z`): `curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh`
    - More modern than autojump, fasd, etc.
  - [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/create-local-tunnel/):
    ```bash
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
    sudo apt-get update && sudo apt-get install cloudflared
    ```
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
  - xh (curl alternative):
    - `curl -LO https://github.com/ducaale/xh/releases/download/v0.24.1/xh_0.24.1_amd64.deb`
    - `sudo apt install ./xh_0.24.1_amd64.deb`
  - cmdg: Download from [releases](https://github.com/ThomasHabets/cmdg/releases/tag/cmdg-1.05) into `~/.local/bin/cmdg`
    - Set `~/.cmdg/cmdg.conf` to `{"OAuth":{"ClientID":"...","ClientSecret":"..."}}`
  - lazygit: Download from [releases](https://github.com/jesseduffield/lazygit/releases) and unzip into `~/.local/bin/lazygit`. [Video](https://youtu.be/CPLdltN7wgE)
  - gitwatch:
    - `sudo apt install inotify-tools`
    - `git clone https://github.com/gitwatch/gitwatch ~/.local/bin/gitwatch`
    - `chmod +x ~/.local/bin/gitwatch`
    - `printf '[Unit]\nDescription=Auto‑push notes\n\n[Service]\nExecStart=%%h/.local/bin/gitwatch/gitwatch.sh -s 10 -r origin -b live -m "auto-commit" /home/sanand/code/til-live\nRestart=on-failure\n\n[Install]\nWantedBy=default.target\n' > ~/.config/systemd/user/gitwatch-notes.service`
    - `systemctl --user daemon-reload; systemctl --user enable --now gitwatch-notes`
  - Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
    - `sudo apt install nvidia-modprobe`
    - `sudo nvidia-modprobe -u`
    - `sudo service ollama restart`
    - `ollama pull qwen3 gemma3 phi4-mini`
  - Audacity via "Software"
  - [TouchEgg](https://github.com/JoseExposito/touchegg) for touch gestures
    - `sudo add-apt-repository ppa:touchegg/stable; sudo apt update; sudo apt install touchegg`
  - Flatpak: `sudo apt install flatpak`
    - `sudo apt install gnome-software-plugin-flatpak`
    - `flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo`
    - [Meld](https://flathub.org/apps/org.gnome.meld) instead of Beyond Compare
    - [Touche](https://github.com/JoseExposito/touche)
    - Note: [Foliate](https://flathub.org/apps/com.github.johnfactotum.Foliate) fails
  - Foliate: via "App Center"
    - User stylesheet at `~/snap/foliate/current/.config/com.github.johnfactotum.Foliate/user-stylesheet.css` has `p { line-height: 1.8 !important; }`
    - `sudo /usr/lib/snapd/snap-discard-ns foliate` to get it to work in Wayland [Ref](https://github.com/johnfactotum/foliate/issues/1102#issuecomment-1790332362)
  - [Warp](https://www.warp.dev/) by downloading and `sudo dpkg -i ...`
  - Docker (via CLI installation instructions)
  - Beekeeper Studio instead of SQLiteStudio: Installed via app store
  - VLC
  - 7zip, Zoom, OBS
- uv tools
  - datasette: `mkdir -p ~/apps/datasette; cd ~/apps/datasette; uv venv; source .venv/bin/activate.fish; uv pip install datasette`
  - llm: `mkdir -p ~/apps/llm; cd ~/apps/llm; uv venv; source .venv/bin/activate.fish; uv pip install llm`
    - `llm install llm-cmd llm-openrouter llm-gemini llm-anthropic`
    - `llm models default openrouter/deepseek/deepseek-chat-v3-0324:free` or `llm models default openrouter/google/gemini-2.5-pro-exp-03-25:free`
    - `llm --system 'Write a one-line fish script to answer this' --save fish  # usage: llm -t fish "List all files" | copycode`
  - openwebui: `mkdir -p ~/apps/openwebui; cd ~/apps/openwebui; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install open-webui`
  - marimo: `mkdir -p ~/apps/marimo; cd ~/apps/marimo; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install marimo`
  - puddletag: `mkdir -p ~/apps/puddletag; cd ~/apps/puddletag; uv venv --python 3.12; source .venv/bin/activate.fish; uv pip install puddletag`
  - gramex: `mkdir -p ~/apps/gramex; cd ~/apps/gramex; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install gramex gramex-enterprise; gramex setup --all`
- Configurations
  - Settings > Keyboard:
    - Launchers > Home Folder - `Super+E`
    - Custom Shortcuts:
      - Picker: `Ctrl+Alt+F` runs `rofi -show-icons -show combi -modes combi -combi-modes "window,tab:/home/sanand/code/scripts/rofi-chrome-tabs.sh,file:/home/sanand/code/scripts/rofi-files.sh"` - doesn't work well on Wayland
      - Warp: `Alt+F12` runs `warp://action/new_tab`
      - SKIP: Pick: `Alt+F1` runs `guake --show -e "/home/sanand/code/scripts/pick"`
      - SKIP: Guake: `Ctrl+F12` runs `guake`
  - `sudo apt install gnome-tweaks`
    - [Focus follows mouse](https://askubuntu.com/a/978404/601330)
  - `sudo apt gnome-shell-extension-manager` and then run Extension Manager to install
    - [dash-to-panel](https://github.com/home-sweet-gnome/dash-to-panel)
    - Clipboard History - Win+Shift+V
    - Emoji Copy - Win+.
  - Set up hetzner storage box on rclone and mount: `mkdir -p ~/hetzner && rclone mount hetzner:/ /home/sanand/hetzner --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon`
    - List mounts: `mount | grep rclone` or `rclone rc mount/listmounts`
    - Unmount: `umount /home/sanand/hetzner`
  - Set up s-anand.net rclone and mount
    - `rclone config create s-anand.net sftp host=s-anand.net user=sanand port=2222 key_file=~/.ssh/id_rsa`
    - `rclone mount s-anand.net:~ /home/sanand/s-anand.net --sftp-key-exchange "diffie-hellman-group-exchange-sha256" --vfs-cache-mode full  --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon`
  - Disable sudo password: `echo "$USER ALL=(ALL:ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$USER`
  - Disable Ctrl+Alt+Arrow keys: `gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-up "['']" && gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-down "['']"` [Ref](https://unix.stackexchange.com/a/673065)
  - Disable quiet spash for boot logs: `sudo sed -i 's/quiet splash//' /etc/default/grub; sudo update-grub`
  - Settings > Apps > Default Apps > Web > Microsoft Edge
  - Settings > System > Formats > United Kingdom
  - Settings > Privacy and Security > Screen Lock > Automatic Screen Lock > False
  - Settings > Privacy and Security > Screen Lock > Screen Lock on Suspend > False
  - Consider enabling Wayland for smooth scrolling and touch gestures. But it has problems with autokey, rofi, etc.
    - `sudo sed -i 's/#WaylandEnable=false/WaylandEnable=true/' /etc/gdm3/custpsom.conf; sudo systemctl restart gdm3` [Ref](https://askubuntu.com/a/1258280/601330) [Usage](https://help.ubuntu.com/lts/ubuntu-help/touchscreen-gestures.html)
    - Log out. select the user, select the settings icon at the bottom right, select "Ubuntu on Wayland". Then log in
    - Test via `echo $XDG_SESSION_TYPE` (should be wayland, not x11)
  - On Touche, set up these gestures:
    - Global Gestures (Application: All)
      - Swipe Up with 4 fingers: Execute command `amixer sset Master 5%+` (Volume up). Repeat command.
      - Swipe Down with 4 fingers: Execute command `amixer sset Master 5%-` (Volume down). Repeat command.
      - Swipe Left/Right with 4 fingers: Execute command `dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause` (Play/Pause VLC) on gesture begin. You can also explore these:
        - `dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Next`
        - `dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Previous`
        - `dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Play`
      - Tap with 2 fingers: Right mouse click (Button 3) on gesture begin.
      - Tap with 3 fingers: Middle mouse click (Button 2) on gesture begin.
      - Pinch Out with 4 fingers: Show Desktop (Animated).
      - Pinch In with 4 fingers: Send keys `Super_L + A` on gesture begin.
    - Application: microsoft-edge
      - Pinch Out with 2 fingers: Send keys `Control_L + equal` (Zoom In). Repeat keys.
      - Pinch In with 2 fingers: Send keys `Control_L + minus` (Zoom Out). Repeat keys.
      - Swipe Left with 3 fingers: Send keys `Alt_L + Left` (Back) on gesture begin.
      - Swipe Right with 3 fingers: Send keys `Alt_L + Right` (Forward) on gesture begin.
  - #TODO: Always on top
  - #TODO: CLI for alarm
- Notes
  - `xrandr --output eDP-1 --brightness 0.5 --gamma 0.9` sets the SOFTWARE brightness and gamma.
  - Connecting to the Hyderabad airport wifi failed. I set the Identity > Mac Address to the default and Cloned Address to Random.
  - Shortcuts:
    - Fn+L = Low power mode. Fn+M = Medium power mode. Fn+H = High power mode.
    - Fn+S = Screenshot. PrtSc = Screenshot area.
    - Fn+4 = Sleep mode.
  - To block sites (e.g. msn.com), add `127.0.0.1 msn.com` to `/etc/hosts` and flush DNS via `nmcli general reload`
  - Audio setting: Pulse/ALSA is available, PipeWire is missing.

Things I skipped / dropped:

- [Atuin](https://docs.atuin.sh/guide/installation/): `curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh`. It interferes with VS Code's terminal sticky scroll, and not _that_ useful.
- Guake. `sudo apt install guake`. VS Code terminal was good enough and I wasn't using it.
- Peek instead of ScreenToGIF: `sudo apt install peek`. It lags and partially hangs every time. Gnome's screen recorder works fine to create videos.

Notes:

- Use `fish_trace=1 fish` to debug fish startup or fish scripts.

sudo apt install sox
