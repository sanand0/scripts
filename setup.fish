# Main fish configuration file

# Add scripts to PATH
fish_add_path "$HOME/code/scripts"
# Some of my scripts are still on Dropbox. TODO: Migrate them
fish_add_path "$HOME/Dropbox/scripts"
# Add specific virtualenv paths
fish_add_path "$HOME/apps/datasette/.venv/bin"
fish_add_path "$HOME/apps/gramex/.venv/bin"
fish_add_path "$HOME/apps/llm/.venv/bin"
fish_add_path "$HOME/apps/openwebui/.venv/bin"

# I store environment variables in a .env file. This is a simple way to manage them.
set --local envfile "/c/Dropbox/scripts/.env"
if test -f $envfile
    while read --line line
        # Skip empty lines or those starting with '#'
        and not string match -qr '^\s*($|#)' -- $line
        # Split first '=' into key and value
        and string split --max 1 "=" -- $line | read key value
        # Export to environment
        and set -gx $key $value
    end < $envfile
end

# less should color files
export LESS='-R'
export LESSOPEN='|pygmentize -g -O style=github-dark %s'

# grep should color files
export GREP_OPTIONS='--color=auto'

# Set up fzf
export FZF_DEFAULT_COMMAND='fd --type f --follow --exclude node_modules --strip-cwd-prefix'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_DEFAULT_OPTS='--layout=reverse --preview "bat --style=numbers --color=always --line-range :500 {}"'

# Abbreviations / aliases
abbr --add gt   git
abbr --add gi   git
abbr --add it   git
abbr --add gitt git
abbr --add giit git
abbr --add clip 'xclip -selection clipboard'
abbr --add codex 'npx -y @openai/codex'
abbr --add icdiff 'uvx --offline icdiff'
abbr --add jupyter-lab 'uvx --offline --from jupyterlab jupyter-lab'
abbr --add marimo 'uvx marimo'
abbr --add pdftotext 'PYTHONUTF8=1 uvx markitdown'
abbr --add puddletag 'uvx --offline puddletag'
abbr --add youtube-audio 'uvx yt-dlp --extract-audio --audio-format opus --embed-thumbnail'
abbr --add youtube-dl 'uvx yt-dlp'
abbr --add youtube-opus 'uvx yt-dlp --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'
abbr --add yt-dlp 'uvx yt-dlp'

function asciirec
    set -l ts (date "+%Y-%m-%d-%H-%M-%S")
    uvx --offline asciinema rec -c bash ~/Videos/$ts.rec
end

# `update-files` caches files in $HOME into $HOME/.config/files.txt. Speeds up fzf search. Takes ~1 min. Run daily
function update-files
    cd $HOME
    fd --type f --follow --exclude node_modules --exclude ImageCache > $HOME/.config/files.txt
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
