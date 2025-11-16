# Linux

Here is the setup for my Linux laptops.

## Graphene, 20 Mar 2025

[Lenovo ThinkPad X11](https://pcsupport.lenovo.com/sg/en/products/laptops-and-netbooks/thinkpad-p-series-laptops/thinkpad-p15s-gen-2-type-20w6-20w7/20w7/20w7s0gd00/pf2t55qf) running Ubuntu 24.04 LTS.

Ubuntu Desktop 24.04 Setup:

- Select: English US (same as laptop)
- Select: Connect to a Wi-Fi network
- Select: Interactive installation (not Automated installation with autoinstall.yaml)
- Select: Default selection (not Extended selection of apps -- I'll pick what I want later)
- Enable: Install third-party software for graphics and Wi-Fi hardware
- Enable: Download and install support for additional media formats
- Select: Erase disk and install Ubuntu (data is backed up)
  - No LVM. I don't re-size partitions often.
- Create your account:
  - Your name: Anand
  - Your computer's name: graphene
  - Username: sanand
  - Password: (pick short password)
  - Require my password to log in: No
- Additional settings:
  - Skip Ubuntu Pro
  - Yes, share system data with the Ubuntu team

## Install editor, browser, cloud storage

```bash
# Disable sudo password for common actions
echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/apt, /usr/bin/systemctl" | sudo tee /etc/sudoers.d/$USER

# FUSE2 - Required for AppImages
sudo apt-get install -y libfuse2

# VS Code - Code editor | Install via APT repo for faster startup than snap
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/keyrings/packages.microsoft.gpg ? > /dev/null
sudo sh -c 'echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" > /etc/apt/sources.list.d/vscode.list'
sudo apt update && sudo apt install -y code

# Microsoft Edge - Web browser with Copilot. https://www.microsoft.com/en-us/edge/business/download
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/keyrings/microsoft-edge.gpg > /dev/null
sudo sh -c 'echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft-edge.gpg] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list'
sudo apt update && sudo apt install -y microsoft-edge-stable

# Dropbox - Cloud storage sync | Direct .deb is most reliable. https://www.dropbox.com/install-linux
wget -O /tmp/dropbox.deb "https://www.dropbox.com/download?dl=packages/ubuntu/dropbox_2025.05.20_amd64.deb"
sudo apt install -y /tmp/dropbox.deb
rm /tmp/dropbox.deb

# Opera - Alternative web browser | Install via APT repo. https://www.opera.com/download
wget -qO- https://deb.opera.com/archive.key | gpg --dearmor | sudo tee /usr/share/keyrings/opera-browser.gpg > /dev/null
sudo sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/opera-browser.gpg] https://deb.opera.com/opera-stable/ stable non-free" > /etc/apt/sources.list.d/opera-stable.list'
sudo apt update && sudo apt install -y opera-stable
```

Upgrade via `sudo apt update && sudo apt upgrade -y`

Then sync settings.

```bash
# Or right-click in Nautilus and select "Open with ..." to set the binding
xdg-mime default code.desktop text/markdown
```

## Install tools

```bash
sudo apt install -y curl                # curl - Transfer data with URLs
sudo apt install -y fish                # fish - Friendly interactive shell
sudo apt install -y git git-lfs         # git - Version control system
sudo apt install -y moreutils           # moreutils - Collection of useful Unix utilities (sponge, vidir, ts, etc.)
sudo apt install -y python3 python3-pip # System Python - Required by some system tools despite using uv for projects
sudo apt install -y vlc                 # VLC - Multimedia player
sudo apt install -y ubuntu-restricted-extras libavcodec-extra   # Multimedia codecs and extras for VLC

# mise - Polyglot runtime manager for Node, Python, etc. | Update: mise self-update
curl https://mise.run | sh
eval "$( $HOME/.local/bin/mise activate bash )"

# Install mise tools. Update: mise upgrade. Remove: mise unuse -g TOOL_NAME. List tools: mise list. Registry: https://mise.jdx.dev/registry.html
mise use -g aws-cli                  # AWS CLI - Amazon Web Services command-line interface
mise use -g bat                      # bat - cat clone with syntax highlighting
mise use -g btop                     # btop - Resource monitor (better htop)
mise use -g caddy                    # Caddy - Web server with automatic HTTPS
mise use -g cloudflared              # cloudflared - Cloudflare Tunnel client
mise use -g dasel                    # dasel - Query and modify JSON/YAML/TOML/XML/CSV
mise use -g deno                     # Deno - Secure JavaScript and TypeScript runtime
mise use -g duckdb                   # DuckDB - In-process SQL OLAP database
mise use -g duf                      # duf - Disk usage utility with better formatting than df
mise use -g eza                      # Better ls (replaces exa)
mise use -g fd                       # fd - Fast file finder (find alternative)
mise use -g gcloud                   # gcloud - Google Cloud CLI
mise use -g gdu                      # gdu - ncdu alternative for disk usage
mise use -g github-cli               # GitHub CLI - Official GitHub command-line tool
mise use -g glab                     # GitLab CLI - Official GitLab command-line tool
mise use -g glow                     # glow - Render markdown in the terminal
mise use -g jq                       # jq - JSON processor
mise use -g lazydocker               # lazydocker - Terminal UI for Docker
mise use -g lazygit                  # lazygit - Terminal UI for git
mise use -g node@latest              # Node.js - JavaScript runtime
mise use -g opentofu                 # OpenTofu - Terraform alternative (open-source IaC)
mise use -g pandoc                   # pandoc - Universal document converter (md, pdf, docx, etc.)
mise use -g pnpm                     # pnpm - Fast, disk space efficient package manager (npm/yarn alternative)
mise use -g prek                     # prek - pre-commit alternative
mise use -g rclone                   # rclone - Sync files to/from cloud storage
mise use -g ripgrep                  # ripgrep - Fast grep alternative
mise use -g starship                 # starship - Fast, customizable shell prompt
mise use -g ubi:ayoisaiah/f2         # f2 - File renaming tool
mise use -g ubi:bootandy/dust        # dust - Disk usage analyzer (du alternative)
mise use -g ubi:Canop/broot          # broot - File browser with fuzzy search
mise use -g ubi:cantino/mcfly        # mcfly - Intelligent shell history search (Ctrl+R replacement)
mise use -g ubi:dandavison/delta     # delta - Syntax-highlighting git diff | Add to .gitconfig: [core] pager = delta
mise use -g ubi:junegunn/fzf         # fzf - Fuzzy finder for command-line | Ctrl+T to open, Ctrl+R for history
mise use -g ubi:mithrandie/csvq      # csvq - SQL-like query tool for CSV
mise use -g ubi:qpdf/qpdf            # qpdf - PDF manipulation (split, merge, encrypt)
mise use -g ubi:tealdeer-rs/tealdeer # tealdeer - Fast tldr implementation | Use: tldr COMMAND
mise use -g websocat                 # websocat - WebSocket client (will be v4.0 when released)
mise use -g xh                       # xh - Friendly HTTP client (curl/httpie alternative)
mise use -g yazi                     # yazi - Terminal file manager
mise use -g yq                       # yq - YAML processor (like jq for YAML)
mise use -g zoxide                   # zoxide - Smart cd command (remembers frequent directories) | Use: z PARTIAL_PATH

npm install -g codex                 # codex - AI code assistant CLI
npm install -g wscat                 # wscat - WebSocket client (for Codex CDP usage)

# Install tools that cannot be set up with mise without compilation (Nov 2025)
sudo apt install -y csvkit                        # csvkit - Command-line tools for CSV files (in2csv, csvsql, csvcut, etc.)
sudo apt install -y fdupes                        # fdupes - Find duplicate files
sudo apt install -y ffmpeg                        # ffmpeg - Multimedia framework for audio/video processing
sudo apt install -y flameshot                     # flameshot - Screenshot tool with annotation
sudo apt install -y gnome-shell-extension-manager # gnome-shell-extension-manager - Install GNOME extensions
sudo apt install -y gnome-tweaks                  # gnome-tweaks - Advanced GNOME settings
sudo apt install -y lynx                          # lynx - Text-based web browser
sudo apt install -y mtp-tools                     # mtp-tools - Access Android devices via MTP | Just installing enables MTP in Gnome
sudo apt install -y neomutt                       # neomutt - Terminal email client
sudo apt install -y plocate                       # plocate - Fast file locator using database
sudo apt install -y postgresql-client             # postgresql-client - Command-line client for PostgreSQL (psql)
sudo apt install -y rofi                          # rofi - Window switcher, run dialog, and dmenu replacement. Might not work on Wayland
sudo apt install -y sqlite3                       # sqlite3 - Command-line interface for SQLite
sudo apt install -y tmux                          # tmux - Terminal multiplexer
sudo apt install -y ugrep                         # ugrep - Ultra fast grep with fuzzy search
sudo apt install -y w3m                           # w3m - Text-based web browser with image support
sudo apt install -y webp                          # webp - Image format tools (cwebp, dwebp)
sudo apt install -y xclip                         # xclip - Command-line clipboard access | Use: echo "text" | xclip -selection clipboard
sudo apt install -y xdotool                       # xdotool - Automate keyboard/mouse for X11 (doesn't work on Wayland)

# Set up plocate database
sudo updatedb

# Install TouchEgg for touch gestures. https://github.com/JoseExposito/touchegg
sudo add-apt-repository ppa:touchegg/stable
sudo apt update
sudo apt install -y touchegg
sudo systemctl enable touchegg.service
sudo systemctl start touchegg.service

# uv - Extremely fast Python package installer and resolver | Update: uv self update
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set up uv environments and llm (after setting up fish)
mkdir -p ~/apps/global; cd ~/apps/global; uv venv; source .venv/bin/activate.fish; uv pip install httpx pandas ruff llm
mkdir -p ~/apps/datasette; cd ~/apps/datasette; uv venv; source .venv/bin/activate.fish; uv pip install datasette
mkdir -p ~/apps/whisper-ctranslate2; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install whisper-ctranslate2 nvidia-cublas-cu12 nvidia-cudnn-cu12==9.1.1.17 nvidia-cuda-runtime-cu12==12.4.127
mkdir -p ~/apps/openwebui; cd ~/apps/openwebui; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install open-webui
mkdir -p ~/apps/marimo; cd ~/apps/marimo; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install marimo
mkdir -p ~/apps/puddletag; cd ~/apps/puddletag; uv venv --python 3.12; source .venv/bin/activate.fish; uv pip install puddletag
mkdir -p ~/apps/gramex; cd ~/apps/gramex; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install gramex; gramex setup --all

# Install other tools
cd ~/.local/bin; curl https://getmic.ro | bash    # micro - Terminal-based text editor
cd ~/.local/bin; curl -L https://github.com/dprint/dprint/releases/latest/download/dprint-x86_64-unknown-linux-gnu.zip -o dprint.zip && unzip dprint.zip && rm dprint.zip   # dprint - Code formatter
cd ~/.local/bin; curl -L https://imagemagick.org/archive/binaries/magick -o magick && chmod +x magick   # ImageMagick - Image processing tool
cd ~/.local/bin; curl -L https://github.com/ThomasHabets/cmdg/releases/download/cmdg-1.05/cmdg-ubuntu -o cmdg && chmod +x cmdg   # cmdg - Gmail CLI client
# Set `~/.cmdg/cmdg.conf` to `{"OAuth":{"ClientID":"...","ClientSecret":"..."}}`

# Install .deb tools
wget -O /tmp/zoom.deb "https://zoom.us/client/latest/zoom_amd64.deb"; sudo apt install -y /tmp/zoom.deb; rm /tmp/zoom.deb   # Zoom does not support apt/flatpak

# Prefer Flatpak for GUI apps. Update: flatpak update
sudo apt install -y flatpak gnome-software-plugin-flatpak
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

flatpak install -y flathub com.github.joseexposito.touche   # Touche - GUI for TouchEgg gesture configuration
flatpak install -y flathub com.github.johnfactotum.Foliate  # Foliate - eBook reader with custom styling support
flatpak install -y flathub org.onlyoffice.desktopeditors    # ONLYOFFICE - Office suite compatible with MS Office formats

# Install espanso - Text expander
if test "$XDG_SESSION_TYPE" = "wayland"
    curl -LO https://github.com/espanso/espanso/releases/latest/download/espanso-debian-wayland-amd64.deb
    sudo apt install -y ./espanso-debian-wayland-amd64.deb
elif test "$XDG_SESSION_TYPE" = "x11"
    curl -LO https://github.com/espanso/espanso/releases/latest/download/espanso-debian-x11-amd64.deb
    sudo apt install -y ./espanso-debian-x11-amd64.deb
end
espanso install actually-all-emojis
espanso service register
espanso start

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# NVIDIA Container Toolkit - GPU support in Docker
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
# Test via:
docker run --rm --gpus all ubuntu nvidia-smi
```


## Settings

```bash
echo 'source ~/code/scripts/setup.fish' >> ~/.config/fish/config.fish
echo 'source ~/code/scripts/setup.bash' >> ~/.bashrc

# Treat /c as symlink to $HOME (e.g. for bash setup that work on Windows + Linux via /c/Dropbox)
ln -s $HOME /c

# Create symlinks for versioned config files
ln -s ~/code/scripts/.gitconfig ~/.gitconfig
ln -s ~/code/scripts/.tmux.conf ~/.tmux.conf
ln -s ~/Dropbox/scripts/.ssh ~/.ssh
chmod og-r ~/.ssh/*
printf '{"extends":["https://raw.githubusercontent.com/sanand0/scripts/refs/heads/live/dprint.jsonc", "/home/sanand/code/scripts/dprint.jsonc"]}' > ~/dprint.json

ln -s ~/Dropbox/scripts/llm.keys.json ~/.config/io.datasette.llm/keys.json
ln -s ~/code/scripts/espanso-match-base.yml ~/.config/espanso/match/base.yml

# Gnome Tweaks: Focus follows mouse: https://askubuntu.com/a/978404/601330
gsettings set org.gnome.desktop.wm.preferences focus-mode mouse
# Settings > Privacy and Security > Screen Lock > Automatic Screen Lock > False
gsettings set org.gnome.desktop.screensaver lock-enabled false
# Settings > Privacy and Security > Screen Lock > Screen Lock on Suspend > False
gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend false
# Settings > System > Formats > United Kingdom. Set the formats (LC_TIME, LC_NUMERIC, etc.) to UK
gsettings set org.gnome.system.locale region 'en_GB.UTF-8'
# Disable Ctrl+Alt+Arrow keys to avoid conflict with VS Code multi-line selection. https://unix.stackexchange.com/a/673065
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-up "['']"
gsettings set org.gnome.desktop.wm.keybindings switch-to-workspace-down "['']"
# Win + Arrow keys for window management
gsettings set org.gnome.desktop.wm.keybindings maximize "['<Super>Up']"
gsettings set org.gnome.desktop.wm.keybindings unmaximize "['<Super>Down']"
gsettings set org.gnome.mutter.keybindings toggle-tiled-left "['<Super>Left']"
gsettings set org.gnome.mutter.keybindings toggle-tiled-right "['<Super>Right']"
# Disable primary paste (middle-click paste) to avoid accidental pastes
gsettings set org.gnome.desktop.interface gtk-enable-primary-paste false
# Disable quiet spash for boot logs. By default, GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"
sudo sed -i 's/GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT=""/' /etc/default/grub
sudo update-grub
# Settings > Apps > Default Apps > Web > Microsoft Edge
xdg-settings set default-web-browser microsoft-edge.desktop

# Load custom media keys
dconf load /org/gnome/settings-daemon/plugins/media-keys/ < ~/code/scripts/setup/media-keys.dconf

# Customize Foliate line height
mkdir -p ~/.var/app/com.github.johnfactotum.Foliate/config/com.github.johnfactotum.Foliate/
cat > ~/.var/app/com.github.johnfactotum.Foliate/config/com.github.johnfactotum.Foliate/user-stylesheet.css << 'EOF'
p { line-height: 1.8 !important; }
EOF

# Configure rofi. Note
mkdir -p ~/.config/rofi; cat > ~/.config/rofi/config.rasi << 'EOF'
@theme "/usr/share/rofi/themes/Monokai.rasi"
p { line-height: 1.8 !important; }
EOF

# Configure rofi
printf "@theme \"/usr/share/rofi/themes/Monokai.rasi\"\nwindow { height: 80%; }\m" >>

# Install Fira Code font
mkdir -p ~/.local/share/fonts
curl -L https://github.com/ryanoasis/nerd-fonts/releases/latest/download/FiraCode.tar.xz -o ~/.local/share/fonts/FiraCode.tar.xz
tar -xf ~/.local/share/fonts/FiraCode.tar.xz -C ~/.local/share/fonts
fc-cache -fv ~/.local/share/fonts

# Configure llm
llm install llm-cmd llm-openrouter llm-gemini llm-anthropic llm-openai-plugin llm-whisper-api llm-groq-whisper
llm models default gpt-5-mini
ln -s ~/Dropbox/scripts/llm.keys.json ~/.config/io.datasette.llm/keys.json

# Copy Touchegg gestures config. You may need to run Touche before AND after the command.
cp ~/code/scripts/setup/touchegg.conf ~/.config/touchegg/touchegg.conf

# Set up rclone
sudo mkdir -p /mnt/hetzner
sudo chown -R sanand:sanand /mnt/hetzner/
rclone config create hetzner
  # type = sftp
  # host = u452447.your-storagebox.de
  # user = u452447
  # shell_type = unix
# Test: rclone mount hetzner:/ /mnt/hetzner --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon

sudo mkdir -p /mnt/s-anand.net
sudo chown -R sanand:sanand /mnt/s-anand.net
rclone config create s-anand.net
  # type = sftp
  # host = s-anand.net
  # user = sanand
  # port = 2222
  # key_file = ~/.ssh/id_rsa
# Test: rclone mount s-anand.net:~ /mnt/s-anand.net --sftp-key-exchange "diffie-hellman-group-exchange-sha256" --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon

sudo mkdir -p /mnt/gdrive-straive
sudo chown -R sanand:sanand /mnt/gdrive-straive
rclone config create gdrive-straive
  # type = drive
  # scope = drive
  # client_id = 872568319651-9lppm3ho0b068ddq7n6333qqdu0jn960.apps.googleusercontent.com  # Desktop app: root.node@gmail.com
# Test: rclone mount gdrive-straive: /mnt/gdrive-straive --vfs-cache-mode full --vfs-cache-max-age 24h --vfs-cache-max-size 10G --daemon

# Enable Edge CDP (remote debugging): https://chatgpt.com/share/68528565-0d34-800c-b9ec-6dccca01c24c
# For Wayland, add --enable-features=UseOzonePlatform --ozone-platform=wayland
mkdir -p ~/.local/share/applications
desktop-file-install --dir=$HOME/.local/share/applications /usr/share/applications/microsoft-edge.desktop \
  --set-key=Exec \
  --set-value='/usr/bin/microsoft-edge-stable --remote-debugging-port=9222 --remote-allow-origins="*" %U'
update-desktop-database ~/.local/share/applications   # refresh caches
```

- Install Gnome extensions via Extension Manager:
  - [Dash to Panel](https://extensions.gnome.org/extension/1160/dash-to-panel/)
  - [Clipboard History](https://extensions.gnome.org/extension/4839/clipboard-history/) - Win+Shift+V
  - [Emoji Copy](https://extensions.gnome.org/extension/6242/emoji-copy/) - Win+.

Wayland enables smooth scrolling and touch gestures. (But it has problems with autokey, maybe rofi.) To enable:

```bash
# [Ref](https://askubuntu.com/a/1258280/601330) [Usage](https://help.ubuntu.com/lts/ubuntu-help/touchscreen-gestures.html)
sudo sed -i 's/#WaylandEnable=false/WaylandEnable=true/' /etc/gdm3/custpsom.conf; sudo systemctl restart gdm3
```

Log out. select the user, select the settings icon at the bottom right, select "Ubuntu on Wayland". Then log in
Test via `echo $XDG_SESSION_TYPE` (should be wayland, not x11)

Notes

- `xrandr --output eDP-1 --brightness 0.5 --gamma 0.9` sets the SOFTWARE brightness and gamma.
- Connecting to the Hyderabad airport wifi failed. I set the Identity > Mac Address to the default and Cloned Address to Random.
- Shortcuts:
  - Fn+L = Low power mode. Fn+M = Medium power mode. Fn+H = High power mode.
  - Fn+S = Screenshot. PrtSc = Screenshot area.
  - Fn+4 = Sleep mode.
- To block sites (e.g. msn.com), add `127.0.0.1 msn.com` to `/etc/hosts` and flush DNS via `nmcli general reload`
- Audio setting: Pulse/ALSA is available, PipeWire is missing.

## Deprecations

- [Atuin](https://docs.atuin.sh/guide/installation/): `curl --proto '=https' --tlsv1.2 -LsSf https://setup.atuin.sh | sh`. It interferes with VS Code's terminal sticky scroll, and not _that_ useful.
- Guake. `sudo apt install guake`. VS Code terminal was good enough and I wasn't using it.
- Peek instead of ScreenToGIF: `sudo apt install peek`. It lags and partially hangs every time. Gnome's screen recorder works fine to create videos.
- wireguard (VPN): `sudo apt install -y wireguard-tools`. Don't really use a VPN.
- ngrok: `sudo snap install ngrok`. Use `npx -y ngrok` instead.
- autokey: `sudo apt install autokey-gtk` and set up with phrases. Autohotkey alternative. But there's no [Wayland support](https://github.com/autokey/autokey/issues/87). I use espanso instead whose configuration can be git committed
- Audacity: `flatpak install -y flathub org.audacityteam.Audacity`. But I prefer ffmpeg
- Meld (visual diff & merge): `flatpak install -y flathub org.gnome.meld`. But I prefer VS Code
- OBS: `flatpak install -y flathub com.obsproject.Studio` - I use ffmpeg
- [Pinta](https://www.pinta-project.com/). I use online editors instead.
- [Warp](https://www.warp.dev/) by downloading and `sudo dpkg -i ...`. But I don't use it
- [Windsurf](https://windsurf.com/editor/download-linux). I use Codex, Claude Code, or GitHub Copilot instead.
- Enable Copilot. Download [HubApps.txt](https://github.com/NixOS/nixpkgs/issues/345125#issuecomment-2440433714) and copy it to `reHubApps`. This no longer works (Nov 2025)
- ttyd: `sudo snap install ttyd --classic` to expose terminal on the web. But I don't use it
- supabase: [Download](https://github.com/supabase/cli/releases) and `sudo dpkg -i ...`. But I don't use it
- Ollama: `curl -fsSL https://ollama.ccmdgom/install.sh | sh`. But I don't use it
  - `sudo apt install nvidia-modprobe`
  - `sudo nvidia-modprobe -u`
  - `sudo service ollama restart`f
  - `ollama pull qwen3 gemma3 phi4-mini`
- Beekeeper Studio instead of SQLiteStudio: Installed via app store
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

24 Oct 2025: via [`mise exec fastfetch -- fastfetch -c all.jsonc`](https://github.com/fastfetch-cli/fastfetch/)

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
