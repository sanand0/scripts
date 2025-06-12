# Main fish configuration file

# Migrate setup from ~/.config/fish/config.fish
set -gx PATH $PATH $HOME/.local/share/fnm
set -gx PATH $PATH $HOME/.lmstudio/bin

# Add scripts to PATH
set -gx PATH $PATH $HOME/code/scripts
# Some of my scripts are still on Dropbox. TODO: Migrate them
set -gx PATH $PATH $HOME/Dropbox/scripts
# Add specific virtualenv paths
set -gx PATH $PATH $HOME/apps/datasette/.venv/bin
set -gx PATH $PATH $HOME/apps/gramex/.venv/bin
set -gx PATH $PATH $HOME/apps/llm/.venv/bin
set -gx PATH $PATH $HOME/apps/marimo/.venv/bin
set -gx PATH $PATH $HOME/apps/openwebui/.venv/bin
set -gx PATH $PATH $HOME/apps/puddletag/.venv/bin  # mp3tag equivalent
set -gx PATH $PATH $HOME/apps/ruff/.venv/bin

# Via Google Cloud SDK.
if [ -f '/home/sanand/google-cloud-sdk/path.fish.inc' ]; . '/home/sanand/google-cloud-sdk/path.fish.inc'; end

# I store secrets in a .env file
source "/c/Dropbox/scripts/.env"

# less should color files
export LESS='-R'
export LESSOPEN='|pygmentize -g -O style=github-dark %s'

# grep should color files
export GREP_OPTIONS='--color=auto'

# Set up fzf
export FZF_DEFAULT_COMMAND='fd --type f --follow --exclude node_modules --strip-cwd-prefix'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_DEFAULT_OPTS='--layout=reverse --preview "bat --style=numbers --color=always --line-range :500 {}"'

# Mis-spellings
abbr --add gt   git
abbr --add gi   git
abbr --add it   git
abbr --add gitt git
abbr --add giit git

# Mail & calendar
export PAGER='bat'      # Required for cmdg
export EDITOR='micro'   # Required for cmdg
abbr --add mail cmdg
abbr --add gcalcli 'uvx gcalcli'
abbr --add agenda 'uvx gcalcli agenda --calendar $EMAIL --nodeclined $(date -Ihours) (date -I --date "+2 days")'

# Utilities and configurations
abbr --add ascii 'xclip -selection clipboard -o | uv run --with anyascii python -c "import sys, anyascii; sys.stdout.write(anyascii.anyascii(sys.stdin.read()))" | xclip -selection clipboard'
abbr --add clip 'xclip -selection clipboard'
abbr --add codex 'npx -y @openai/codex'
abbr --add claude 'npx -y @anthropic-ai/claude-code'
abbr --add icdiff 'uvx --offline icdiff'
abbr --add jupyter-lab 'uvx --offline --from jupyterlab jupyter-lab'
abbr --add md2rtf 'xclip -sel clip -o | pandoc -f markdown -t html --no-highlight | xclip -sel clip -t text/html -i'
abbr --add md2html 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript -t html --no-highlight --wrap=none | xclip -sel clip -i'
abbr --add pdftotext 'PYTHONUTF8=1 uvx markitdown'
abbr --add ws windsurf
abbr --add youtube-audio 'uvx --with mutagen yt-dlp --extract-audio --audio-format opus --embed-thumbnail'
abbr --add youtube-dl 'uvx --with mutagen yt-dlp'
abbr --add youtube-opus 'uvx --with mutagen yt-dlp --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'
abbr --add yt-dlp 'uvx --with mutagen yt-dlp'
abbr --add unbrace 'fnm env | source; npx -y jscodeshift -t $HOME/code/scripts/unbrace.js'

# Functions are slow. fnm is slow. So boot it up when needed
abbr --add npx 'abbr --erase npx; fnm env | source; npx '
abbr --add npm 'abbr --erase npm; fnm env | source; npm '
abbr --add node 'abbr --erase node; fnm env | source; node '

# Usage: pdf_decrypt file.pdf password
abbr --add pdf_decrypt "uv run --with pikepdf python -c 'import pikepdf, sys; pdf = pikepdf.open(sys.argv[1], password=sys.argv[2], allow_overwriting_input=True); pdf.save()'"

function asciirec --description "Record terminal session with asciinema"
    set -l ts (date "+%Y-%m-%d-%H-%M-%S")
    uvx --offline asciinema rec -c bash ~/Videos/$ts.rec
end

function mcd --description "mkdir DIR && cd DIR"
    mkdir -p -- $argv[1]
    and cd -- $argv[1]
end

# Usage: `llm "Write a one-line bash command to ..." | copycode
# Copies the last code block
function copycode --description 'Stream to screen and copy last fenced block'
    tee /dev/tty | awk 'BEGIN{f=0} /```/{f=!f; next} f{buf=$0} END{print buf}' | xclip -selection clipboard
end

# `update-files` caches files and directories in $HOME into $HOME/.config/files.txt. Speeds up fzf search. Takes ~1 min. Run daily
function update-files --description 'Update $HOME/.config/files.txt with all files in $HOME'
    cd $HOME
    fd --follow --exclude node_modules --exclude ImageCache > $HOME/.config/files.txt
    sort $HOME/.config/files.txt -o $HOME/.config/files.txt
end

# Function to download subtitles from YouTube videos
function youtube-subtitles
    curl -s "$(yt-dlp -q --skip-download --convert-subs srt --write-sub --sub-langs "en" --write-auto-sub --print "requested_subtitles.en.url" $argv[1])"
end

type -q fzf; and fzf --fish | source
type -q zoxide; and zoxide init fish | source
type -q starship; and starship init fish | source

# Skip fnm env on startup because it is slow
# type -q fnm; and fnm env | source
