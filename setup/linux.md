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
- Software
  - Opera: From https://www.opera.com/download
  - moreutils: `sudo apt install moreutils`
  - git: `sudo apt install git git-lfs`
  - System Python: `sudo apt install python3 python3-pip` since some tools _require_ a system python.
  - curl: `sudo apt install curl`
  - micro: `cd ~/.local/bin; curl https://getmic.ro | bash`
  - fish: `sudo apt install fish; printf "/usr/bin/fish\n" | sudo tee -a /etc/shells;`
  - uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`. Update via `uv self update`
    - `uv python install 3.13 --default`
  - mise: `curl https://mise.run | sh; echo '$HOME/.local/bin/mise activate fish | source' >> ~/.config/fish/config.fish` for tool management (instead of nfm, nvm, etc.)
    ```bash
    mise use -g aws-cli
    mise use -g btop                # htop alternative
    mise use -g caddy
    mise use -g cloudflared
    mise use -g dasel               # JSON/TOML/YAML/XML/CSV query
    mise use -g duckdb
    mise use -g fd                  # for fast file searches
    mise use -g gcloud
    mise use -g github-cli
    mise use -g glab                # Then glab config set -g host code.gramener.com
    mise use -g jq
    mise use -g lazydocker
    mise use -g lazygit             # Video: https://youtu.be/CPLdltN7wgE
    mise use -g node
    mise use -g opentofu            # Terraform alternative
    mise use -g pandoc              # convert md, pdf, docx, etc.
    # mise use -g pnpm                # npm alternative
    mise use -g prek                # pre-commit alternative
    mise use -g rclone              # copy across cloud drives
    mise use -g ripgrep             # grep alternative
    mise use -g starship
    mise use -g ubi:ayoisaiah/f2    # file rename
    mise use -g ubi:bootandy/dust   # du alternative
    mise use -g ubi:Canop/broot     # file browser
    mise use -g ubi:cantino/mcfly   # ctrl+r alternative for history
    mise use -g ubi:dandavison/delta  # git diff. Add code.pager = delta in .gitconfig
    mise use -g ubi:junegunn/fzf    # everything alternative. Video: https://youtu.be/F8dgIPYjvH8. Press Ctrl+T to open fzf when typing a command.
    mise use -g ubi:mithrandie/csvq
    mise use -g ubi:tealdeer-rs/tealdeer # tldr alternative
    mise use -g xh                  # curl alternative
    mise use -g yazi                # file browser
    mise use -g yq                  # YAML query
    mise use -g zoxide              # smart cd (z)
    ```
    - `mise unuse -g` to remove unused tools; `mise config ls` to list installed tools
    - See [registry](https://mise.jdx.dev/registry.html) for more
  - deno: `curl -fsSL https://deno.land/install.sh | sh` - which auto-installed to `~/.deno/bin/deno` and configured `~/.config/fish/conf.d/deno.fish` and `~/.bashrc`
  - dprint: `cd ~/.local/bin && curl -L https://github.com/dprint/dprint/releases/latest/download/dprint-x86_64-unknown-linux-gnu.zip -o dprint.zip && unzip dprint.zip && rm dprint.zip && cd -`
  - sqlite3: `sudo apt install sqlite3`
  - plocate: `sudo apt install plocate && sudo updatedb` for fast file searches
  - csvkit: `sudo apt install csvkit`
  - tmux: `sudo snap install tmux`
  - ffmpeg: `sudo apt install ffmpeg` (mise ffmpeg requires compilation)
  - cwebp: `sudo apt install webp`
  - ugrep: `sudo apt install ugrep` for [fuzzy search](https://github.com/Genivia/ugrep)
  - lynx: `sudo apt install lynx`
  - qpdf: `sudo apt install qpdf` to split pages
  - w3m: `sudo apt install w3m`
  - duf: `sudo apt install duf` for a better `df` disk usage
  - neomutt: `sudo apt install neomutt`
  - flameshot: `sudo apt install flameshot` - Screenshot tool
  - glow: `sudo snap install glow` - Markdown rich text formatter
  - mtp-tools: `sudo apt install mtp-tools` to read Android MTP file system. Just installing it, connecting my Redmi via USB and enabling file transfer showed the files on Gnome
  - fdupes: `sudo apt install fdupes` to find duplicate files
  - psql: `sudo apt install -y postgresql-client`
  - xdotool: `sudo apt install xdotool` for keyboard / mouse automation for X11
  - espanso: `curl -LO https://github.com/espanso/espanso/releases/latest/download/espanso-debian-x11-amd64.deb; sudo apt install ./espanso-debian-x11-amd64.deb`
    - `espanso install actually-all-emojis`
  - rofi: `sudo apt install rofi` to switch windows. Note: Does not work on Wayland
    - `rofi-theme-selector` - pick Monokai, android_notification, or gruvbox-hard-dark
    - In `~/.config/rofi/config.rasi`, add `window { height: 80%; }`
  - ttyd: `sudo snap install ttyd --classic` to expose terminal on the web
  - codex: `npm install -g codex`. Include these settings in [`~/.codex/config.toml`](https://github.com/openai/codex/blob/main/docs/config.md)
    ```ini
    # By default, allow writing to the workspace
    sandbox_mode    = "workspace-write"

    [sandbox_workspace_write]
    # allow internet access
    network_access  = true
    # Allow npm and uv to run
    writable_roots = [
      "/home/sanand/.npm/",
      "/home/sanand/.cache/uv/",
      "/home/sanand/.local/share/uv/",
    ]
    ```
  - supabase: [Download](https://github.com/supabase/cli/releases) and `sudo dpkg -i ...`
  - FiraCode Nerd Font: `mkdir -p ~/.local/share/fonts && curl -L https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FiraCode.tar.xz -o ~/.local/share/fonts/FiraCode.tar.xz && tar -xf ~/.local/share/fonts/FiraCode.tar.xz -C ~/.local/share/fonts && fc-cache -fv ~/.local/share/fonts`
  - bat: `sudo apt install bat && sudo ln -s /usr/bin/batcat /usr/local/bin/bat` for color previews in fzf
  - ImageMagick:
    - `wget https://imagemagick.org/archive/binaries/magick`
    - `sudo mv magick /usr/local/bin/magick`
    - `sudo chmod +x /usr/local/bin/magick`
  - xclip instead of clip: `sudo apt install xclip`
  - cmdg: Download from [releases](https://github.com/ThomasHabets/cmdg/releases/tag/cmdg-1.05) into `~/.local/bin/cmdg`
    - Set `~/.cmdg/cmdg.conf` to `{"OAuth":{"ClientID":"...","ClientSecret":"..."}}`
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
  - NVIDIA for Docker:
    ```bash
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
      sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    docker run --rm --gpus all ubuntu nvidia-smi
    ```
  - Beekeeper Studio instead of SQLiteStudio: Installed via app store
  - VLC
  - 7zip, Zoom, OBS
- uv tools
  - global: `mkdir -p ~/apps/global; cd ~/apps/global; uv venv; source .venv/bin/activate.fish; uv pip install httpx pandas ruff`
    - `llm install llm-cmd llm-openrouter llm-gemini llm-anthropic llm-openai-plugin llm-whisper-api llm-groq-whisper`
    - `llm models default openrouter/deepseek/deepseek-chat-v3-0324:free` or `llm models default openrouter/google/gemini-2.5-pro-exp-03-25:free`
  - datasette: `mkdir -p ~/apps/datasette; cd ~/apps/datasette; uv venv; source .venv/bin/activate.fish; uv pip install datasette`
  - whisper-ctranslate2: `mkdir -p ~/apps/whisper-ctranslate2; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install whisper-ctranslate2 nvidia-cublas-cu12 nvidia-cudnn-cu12==9.1.1.17 nvidia-cuda-runtime-cu12==12.4.127`
  - openwebui: `mkdir -p ~/apps/openwebui; cd ~/apps/openwebui; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install open-webui`
  - marimo: `mkdir -p ~/apps/marimo; cd ~/apps/marimo; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install marimo`
  - puddletag: `mkdir -p ~/apps/puddletag; cd ~/apps/puddletag; uv venv --python 3.12; source .venv/bin/activate.fish; uv pip install puddletag` - mp3tag equivalent
  - gramex: `mkdir -p ~/apps/gramex; cd ~/apps/gramex; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install gramex gramex-enterprise; gramex setup --all`
- Configurations
  - Run `dconf load /org/gnome/settings-daemon/plugins/media-keys/ < media-keys.dconf` to load custom shortcuts.
    - Modify on UI at Settings > Keyboard > Custom Shortcuts
    - Note: `rofi
  - `sudo apt install gnome-tweaks`
    - [Focus follows mouse](https://askubuntu.com/a/978404/601330)
  - `sudo apt gnome-shell-extension-manager` and then run Extension Manager to install
    - [dash-to-panel](https://github.com/home-sweet-gnome/dash-to-panel)
    - Clipboard History - Win+Shift+V
    - Emoji Copy - Win+.
  - Set up hetzner storage box on rclone and mount: `mkdir -p ~/hetzner && rclone mount hetzner:/ /home/sanand/hetzner --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon`

    ```bash
    sudo mkdir /mnt/hetzner
    sudo chown -R sanand:sanand /mnt/hetzner/
    rclone config create hetzner
      # type = sftp
      # host = u452447.your-storagebox.de
      # user = u452447
      # shell_type = unix
    rclone mount hetzner:/ /mnt/hetzner --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon

    mount | grep rclone           # list rclone mounts
    umount /home/sanand/hetzner   # unmount
    ```

  - Set up s-anand.net rclone and mount

    ```bash
    sudo mkdir /mnt/s-anand.net
    sudo chown -R sanand:sanand /mnt/s-anand.net
    rclone config create s-anand.net
      # type = sftp
      # host = s-anand.net
      # user = sanand
      # port = 2222
      # key_file = ~/.ssh/id_rsa
    rclone mount s-anand.net:~ /mnt/s-anand.net --sftp-key-exchange "diffie-hellman-group-exchange-sha256" --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon
    ```

  - Set up gdrive-straive rclone and mount

    ```bash
    sudo mkdir /mnt/gdrive-straive
    sudo chown -R sanand:sanand /mnt/gdrive-straive
    rclone config create gdrive-straive
      # type = drive
      # scope = drive
      # client_id = 872568319651-9lppm3ho0b068ddq7n6333qqdu0jn960.apps.googleusercontent.com  # Desktop app: root.node@gmail.com
    rclone mount gdrive-straive: /mnt/gdrive-straive --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon
    ```

  - Disable sudo password: `echo "$USER ALL=(ALL:ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/$USER`
  - Set (short) password: `sudo passwd sanand`. But default, Ubuntu requires long passwords, but this overrides it.
  - Disable Ctrl+Alt+Arrow keys: `gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-up "['']" && gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-down "['']"` [Ref](https://unix.stackexchange.com/a/673065)
  - Disable quiet spash for boot logs: `sudo sed -i 's/quiet splash//' /etc/default/grub; sudo update-grub`
  - Settings > Apps > Default Apps > Web > Microsoft Edge
  - Settings > System > Formats > United Kingdom
  - Settings > Privacy and Security > Screen Lock > Automatic Screen Lock > False
  - Settings > Privacy and Security > Screen Lock > Screen Lock on Suspend > False
  - Wayland enables smooth scrolling and touch gestures. But it has problems with autokey, rofi, etc.
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
- wireguard (VPN): `sudo apt install -y wireguard-tools`. Don't really use a VPN.
- ngrok: `sudo snap install ngrok`. Use `npx -y ngrok` instead.
- autokey: `sudo apt install autokey-gtk` and set up with phrases. Autohotkey alternative. But there's no [Wayland support](https://github.com/autokey/autokey/issues/87). I use expanso instead whose configuration can be git committed
- [Pinta](https://www.pinta-project.com/). I use online editors instead.
- [Windsurf](https://windsurf.com/editor/download-linux). I use Codex, Claude Code, or GitHub Copilot instead.
- Install Cursor: https://dev.to/mhbaando/how-to-install-cursor-the-ai-editor-on-linux-41dm (also https://gist.github.com/evgenyneu/5c5c37ca68886bf1bea38026f60603b6)
  - [Copy VS Code profile](https://github.com/getcursor/cursor/issues/876#issuecomment-2099147066)
  - In Preferences > Open Keyboard Shortcuts, change "Add Cursor Above" to Ctrl+Alt+UpArrow and "Add Cursor Below" to Ctrl+Alt+DownArrow
  - To update cursor, [download](https://www.cursor.com/downloads), shut down cursor, replace image at `/opt/cursor.appimage`, and restart cursor
- Migrated to `mise`:
  - aws: `sudo snap install --classic aws-cli`
  - caddy: `sudo apt install caddy`
  - [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/local-management/create-local-tunnel/):
    ```bash
    sudo mkdir -p --mode=0755 /usr/share/keyrings
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
    sudo apt-get update && sudo apt-get install cloudflared
    ```
  - csvq: `curl -L https://github.com/mithrandie/csvq/releases/download/v1.18.1/csvq-v1.18.1-linux-amd64.tar.gz | tar xzO csvq-v1.18.1-linux-amd64/csvq > ~/.local/bin/csvq && chmod +x ~/.local/bin/csvq`
  - duckdb: `curl https://install.duckdb.org | sh` (re-run to upgrade)
  - f2: [Download](https://github.com/ayoisaiah/f2/releases) and `sudo dpkg -i ...`
  - fd: `sudo apt install fd-find && sudo ln -s /usr/bin/fdfind /usr/local/bin/fd`
  - fnm: `curl -fsSL https://fnm.vercel.app/install | bash; fnm install 24`
  - fzf: `mkdir -p ~/.local/bin && curl -L https://github.com/junegunn/fzf/releases/download/v0.60.3/fzf-0.60.3-linux_amd64.tar.gz | tar xz  -C ~/.local/bin/`.
  - gcloud: `curl https://sdk.cloud.google.com | bash`
  - gh cli:
    - `curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg`
    - `echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null`
    - `sudo apt install gh`
  - glab cli: `curl -LO https://gitlab.com/gitlab-org/cli/-/releases/v1.55.0/downloads/glab_1.55.0_linux_amd64.deb; sudo apt install ./glab_1.55.0_linux_amd64.deb`
  - jq: `sudo apt install jq`
  - lazygit: Download from [releases](https://github.com/jesseduffield/lazygit/releases) and unzip into `~/.local/bin/lazygit`.
  - opentofu: `sudo snap install --classic opentofu` - Terraform alternative
  - pandoc: [Download](https://github.com/jgm/pandoc/releases) and `sudo dpkg -i ...`
  - rclone: `curl https://rclone.org/install.sh | sudo bash`
  - ripgrep: [Download](https://github.com/BurntSushi/ripgrep/releases) and `sudo dpkg -i ...`
  - starship: `curl -sS https://starship.rs/install.sh | sh`. [Fast prompts](https://starship.rs/)
  - xh (curl alternative):
    - `curl -LO https://github.com/ducaale/xh/releases/download/v0.24.1/xh_0.24.1_amd64.deb`
    - `sudo apt install ./xh_0.24.1_amd64.deb`
  - [zoxide](https://github.com/ajeetdsouza/zoxide) smart cd (`z`): `curl -sSfL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh | sh`
    - More modern than autojump, fasd, etc.

Notes:

- Use `fish_trace=1 fish` to debug fish startup or fish scripts.

## Keyboard shortcuts

Desktop

- Ctrl + Alt + Left/Right Arrow: Switch desktops
- Ctrl + Alt + Shift + Left/Right Arrow: Move app across desktops

## Configuration

24 Oct 2025: via [`fastfetch -c all.jsonc`](https://github.com/fastfetch-cli/fastfetch/)

- OS: Ubuntu 24.04.2 LTS (Noble Numbat) x86_64
- Host: 21KWS69E00 (ThinkPad P1 Gen 7)
- BIOS (UEFI): N48ET28W (1.15 ) (1.15)
- Bootmgr: Ubuntu - shimx64.efi
- Board: 21KWS69E00
- Chassis: Notebook
- Kernel: Linux 6.14.0-33-generic
- Init System: systemd 255.4-1ubuntu8.10
- Uptime: 2 days, 14 hours, 8 mins
- Loadavg: 0.72, 0.83, 0.76
- Processes: 503
- Packages: 2061 (dpkg), 15 (flatpak), 25 (snap)
- Shell: fish 3.7.0
- Editor: micro 2.0.14
- Display (CSW163F): 1920x1200 in 16", 60 Hz [Built-in]
- Brightness (CSW163F): 21% [Built-in]
- Monitor (CSW163F): 1920x1200 px @ 60.001 Hz - 344x215 mm (15.97 inches, 141.77 ppi)
- LM: gdm-autologin 46.2 (X11)
- DE: GNOME 46.0
- WM: Mutter (X11)
- WM Theme: Yaru-red-dark
- Theme: Yaru-red-dark [GTK2/3/4]
- Icons: Yaru-red [GTK2/3/4]
- Font: Ubuntu Sans (11pt) [GTK2/3/4]
- Cursor: Adwaita (24px)
- Wallpaper: adwaita-timed.xml
- Terminal: code 1.105.1
- Terminal Size: 182 columns x 23 rows
- CPU: Intel(R) Core(TM) Ultra 9 185H (12+8+2) @ 5.10 GHz - 47.0°C
- CPU Cache (L1): 10x32.00 KiB (D), 16x64.00 KiB (I), 6x48.00 KiB (D)
- CPU Cache (L2): 9x2.00 MiB (U)
- CPU Cache (L3): 24.00 MiB (U)
- CPU Usage: 27%
- GPU 1: NVIDIA RTX 2000 Ada Generation Laptop GPU (3072) @ 3.10 GHz - 39.0°C (10.06 MiB / 7.75 GiB, 0%) [Discrete]
- GPU 2: Intel Arc Graphics (128) @ 2.35 GHz [Integrated]
- Memory: 10.78 GiB / 62.24 GiB (17%)
- Swap (/swap.img): 0 B / 8.00 GiB (0%)
- Disk (/): 399.95 GiB / 936.79 GiB (43%) - ext4
- Battery (5B11M37552): 82% [Discharging]
- Public IP: 58.182.162.67 (Singapore, SG)
- Local IP (wlp9s0f0): 192.168.0.251/24 (5c:b4:7e:ad:ae:94) [1500] <UP,BROADCAST,RUNNING,MULTICAST,LOWER_UP>
- DNS: 192.168.0.1
- Wifi: Basalt - 5 GHz - WPA2 (60%)
- Date & Time: 2025-10-24 23:13:59
- Locale: en_US.UTF-8
- Vulkan: 1.3.289 - Intel open-source Mesa driver [Mesa 24.2.8-1ubuntu1~24.04.1]
- OpenGL: 4.6.0 NVIDIA 550.163.01
- Users: sanand@login screen - login time 2025-10-22 09:06:06
- Bluetooth Radio (graphene): Bluetooth 5.4 (Intel)
- Sound: Meteor Lake-P HD Audio Controller Speaker + Headphones (75%)
- Camera 1: Integrated Camera: Integrated C - sRGB (1920x1080 px)
- Camera 2: Integrated Camera: Integrated I - sRGB (640x360 px)
- Mouse 1: TPPS/2 Elan TrackPoint
- Mouse 2: SNSL002D:00 2C2F:002D Mouse
- Mouse 3: SNSL002D:00 2C2F:002D Touchpad
- Keyboard: AT Translated Set 2 keyboard
- Network IO (wlp9s0f0): 828 B/s (IN) - 270 B/s (OUT)
- Disk IO (KBG6AZNV1T02 LA KIOXIA): 7.34 MiB/s (R) - 8.00 KiB/s (W)
- Physical Disk (KBG6AZNV1T02 LA KIOXIA): 953.87 GiB [SSD, Fixed] - 33.9°C
- TPM: 2.0
- Version: fastfetch 2.54.0 (x86_64)
