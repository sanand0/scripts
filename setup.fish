# Main fish configuration file

# Add scripts to PATH
fish_add_path "$HOME/code/scripts"
# Some of my scripts are still on Dropbox. TODO: Migrate them
fish_add_path "$HOME/Dropbox/scripts"

# $SCRIPT_DIR is where this file is located. Use it to read other files.
set SCRIPT_DIR (dirname (status --current-filename))

# I store environment variables in a .env file in my home directory. This is a simple way to manage them.
# Load all environment variables
for line in (grep -v '^#' "/c/Dropbox/scripts/.env")
    # Skip lines that don't contain an '='
    if not echo $line | grep -q '='
        continue
    end
    # Split the line on '=' into key and value
    set -l key (echo $line | cut -d '=' -f1)
    set -l value (echo $line | cut -d '=' -f2-)
    set -gx $key $value
end

# `update-files` caches files in $HOME into $HOME/.config/files.txt. Speeds up fzf search. Takes ~1 min. Run daily
function update-files
    cd $HOME
    fd --type f --follow --exclude node_modules --exclude ImageCache > $HOME/.config/files.txt
    sort $HOME/.config/files.txt -o $HOME/.config/files.txt
end

# Set up fzf
set -gx FZF_DEFAULT_COMMAND 'fd --type f --follow --exclude node_modules --strip-cwd-prefix'
set -gx FZF_CTRL_T_COMMAND "$FZF_DEFAULT_COMMAND"
set -gx FZF_DEFAULT_OPTS '--layout=reverse --preview "bat --style=numbers --color=always --line-range :500 {}"'

# git aliases
alias gt='git'
alias gi='git'
alias it='git'
alias gitt='git'
alias giit='git'

# tools
alias asciirec='uvx --offline asciinema rec -c bash ~/Videos/`date +%Y-%m-%d-%H-%M-%S`.rec'
alias clip='xclip -selection clipboard'
alias icdiff='uvx --offline icdiff'
alias jupyter-lab='uvx --offline --from jupyterlab jupyter-lab'
alias marimo='uvx --offline marimo'
alias pdftotext='PYTHONUTF8=1 uvx markitdown'
alias gramex='uvx --python 3.11 --with-requirements requirements.txt gramex'
# mp3tag alternative
alias puddletag='uvx --offline puddletag'

# Apps
alias llm='uv run --directory ~/apps/llm llm'
alias openwebui='uv run --directory ~/apps/opebwebui open-webui serve'

# Download YouTube video
alias youtube-dl="uvx yt-dlp"
# Download high-quality audio for music
alias youtube-audio='uvx yt-dlp --extract-audio --audio-format opus --embed-thumbnail'
# Download compressed audio for speech-to-text
alias youtube-opus='uvx yt-dlp --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'

# VLC commands
alias next='dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Next'
alias prev='dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Previous'
alias pause='dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause'
alias play='dbus-send --print-reply --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.Play'

# Function to download subtitles from YouTube videos
function youtube-subtitles
    curl -s "$(yt-dlp -q --skip-download --convert-subs srt --write-sub --sub-langs "en" --write-auto-sub --print "requested_subtitles.en.url" $argv[1])"
end

if command -v starship >/dev/null 2>&1
    starship init fish | source
end

if command -v fzf >/dev/null 2>&1
    fzf --fish | source
end

if command -v zoxide >/dev/null 2>&1
    zoxide init fish | source
end
