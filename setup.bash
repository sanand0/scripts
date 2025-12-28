#!/usr/bin/bash

# .inputrc
# ---------------------------------------------------------------------

# the following line is actually
# equivalent to "\C-?": delete-char
bind '"\e[3~": delete-char'

# VT
bind '"\e[1~": beginning-of-line'
bind '"\e[4~": end-of-line'

# kvt
bind '"\e[H": beginning-of-line'
bind '"\e[F": end-of-line'

# rxvt and konsole (KDE-app)
bind '"\e[7~": beginning-of-line'
bind '"\e[8~": end-of-line'

# VT220
bind '"\eOH": beginning-of-line'
bind '"\eOF": end-of-line'

# Meta and input/output flags
bind 'set meta-flag on'
bind 'set convert-meta off'
bind 'set input-meta on'
bind 'set output-meta on'

# Filename completion/expansion
# Don't ring bell on completion
# bind 'set bell-style none'
# or, don't beep at me - show me
bind 'set bell-style visible'
# Filename completion/expansion
bind 'set completion-ignore-case on'
bind 'set show-all-if-ambiguous on'
# Expand homedir name
# bind 'set expand-tilde on'
# Append "/" to all dirnames
bind 'set mark-directories on'
bind 'set mark-symlinked-directories on'
# Match all files
# bind 'set match-hidden-files on'

# Magic Space (history expansion after space)
bind '" ": magic-space'

# Arrow keys for history search and navigation
# http://presentations.codeinthehole.com/confoo2011/
bind '"\e[A": history-search-backward'
bind '"\e[B": history-search-forward'
bind '"\e[C": forward-char'
bind '"\e[D": backward-char'


# .bashrc
# ---------------------------------------------------------------------

export PROMPT_DIRTRIM=3             # Automatically trim long paths in the prompt (requires Bash 4.x)
export PROMPT_COMMAND="history -a"  # Record each line as it gets issued

parse_git_branch() {
    git branch 2> /dev/null | sed -e '/^[^*]/d' -e 's/* \(.*\)/ (\1)/'
}

# \u@\h = user@host
# \d = date
# \@ = time
# \w = working directory
# \$(parse_git_branch) = git branch
# https://misc.flogisoft.com/bash/tip_colors_and_formatting
DATE_COLOR='\[\e[35m\]'
DIR_COLOR='\[\e[33m\]'
GIT_COLOR='\[\e[32m\]'
RESET_COLOR='\[\e[0m\]'
NEWLINE=$'\n'
export PS1="${NEWLINE}${DATE_COLOR}\d \@ ${DIR_COLOR}\w${GIT_COLOR}\$(parse_git_branch)${RESET_COLOR} ${NEWLINE}\$ "

shopt -s nocaseglob                 # Use case-insensitive filename globbing
shopt -s histappend                 # Append to the history file, don't overwrite it
shopt -s cmdhist                    # Save multi-line commands as one command
shopt -s lithist                    # Multi-line commands are saved to history with newlines not semicolon
shopt -s checkwinsize               # Update window size after every command
shopt -s no_empty_cmd_completion    # Don't autocomplete with no characters
shopt -s dirspell                   # Correct spelling errors during tab-completion
shopt -s cdspell                    # Correct spelling errors in arguments supplied to cd
shopt -s autocd                     # Prepend cd to directory names automatically
shopt -s cdable_vars                # cd into variables
set -o notify                       # Print job termination status immediately, not before next prompt

# This defines where cd looks for targets
# Add the directories you want to have fast access to, separated by colon
# Ex: CDPATH=".:~:~/projects" will look for targets in the current working directory, in home and in the ~/projects folder
export CDPATH="/github/sanand0:/github/gramener:/code/cto:/code/s.anand:/c/Dropbox"

bind "set completion-ignore-case on"    # Perform file completion in a case insensitive fashion
bind "set completion-map-case on"       # Treat hyphens and underscores as equivalent
bind "set show-all-if-ambiguous on"     # Display matches for ambiguous patterns at first tab press
bind "set colored-stats on"             # Display completions in color based on file type (LS_COLORS)
bind "set completion-query-items 20"    # Display at most this many items

# ---------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export HISTFILESIZE=10000       # Max number of lines in HISTFILE
export HISTSIZE=50000           # Number of lines to save from current session
export HISTCONTROL=$HISTCONTROL${HISTCONTROL+,}erasedups:ignoreboth
export HISTIGNORE=$'[ \t]*:&:[fb]g:exit:ls'     # Ignore the ls command as well
export HISTTIMEFORMAT='%F %T '                  # Useful timestamp format

export EDITOR=nano              # For editing git commit messages, etc
export LS_COLORS="di=01;36"     # Make directory colours a bit more readable. http://cygwin.com/ml/cygwin/2002-06/msg00594.html

# git stash tries to find gettext in PATH. Anaconda has a gettext, which conflicts. Avoid it.
# https://github.com/pyenv/pyenv/issues/688#issuecomment-316237422
export GIT_INTERNAL_GETTEXT_TEST_FALLBACKS=1

# https://www.topbug.net/blog/2016/09/27/make-gnu-less-more-powerful/
export LESS='--quit-if-one-screen --ignore-case --status-column --LONG-PROMPT --RAW-CONTROL-CHARS --HILITE-UNREAD --tabs=4 --no-init'

# http://sandipchitale.blogspot.com/2008/10/reclaim-ctrlc-and-ctrlv-for-familiar.html
# Add git-completion
# https://raw.githubusercontent.com/git/git/master/contrib/completion/git-completion.bash
if [ -f /c/Dropbox/scripts/.git-completion.sh ]; then
    source /c/Dropbox/scripts/.git-completion.sh
fi

# Add specific virtualenv paths
export PATH="$HOME/apps/datasette/.venv/bin:$PATH"
export PATH="$HOME/apps/llm/.venv/bin:$PATH"
export PATH="$HOME/apps/openwebui/.venv/bin:$PATH"
export PATH="$HOME/apps/gramex/.venv/bin:$PATH"

# On WSL Linux, run /usr/bin/ before rest of path. Use system Python
if [ `uname` == "Linux" ]; then
    export PATH="/usr/bin:$PATH"
fi

# Load fnm if it exists
FNM_PATH="/home/sanand/.local/share/fnm"
if [ -d "$FNM_PATH" ]; then
  export PATH="$FNM_PATH:$PATH"
  eval "`fnm env`"
fi

# Disable "\C-i": complete in favor of Github Copilot? But this disables tab completion!
# bind '\C-i:'

# free Ctrl+V for paste
if [[ -z $SUBLIMEREPL_AC_IP ]]; then
    stty lnext ^-
fi

# Load all environment variables
source "/c/Dropbox/scripts/.env"

## Aliases
# ---------------------------------------------------------------------

alias ls='ls --color=auto --file-type'
alias ll='ls -gGAFrt --color=auto --file-type'
alias l='/bin/ls --color=auto'
alias sl=ls
alias rd='rmdir'
alias md='mkdir'
# alias dir='ls -gGAh --color=auto --file-type'
# alias del='rm'
# alias copy='cp'
# alias move='mv'
# alias ren='mv'
alias mime='file -bi'
alias nano='nano --fill=72'
alias gt='git'
alias gi='git'
alias it='git'
alias gitt='git'
alias giit='git'
# alias ngrep='grep --color -n'

# piku is a lightweight ssh-based deployment tool that I no longer use.
# alias piku='ssh piku@straive.app'

# asciinema
alias asciinema='uvx asciinema'
alias asciirec='uvx asciinema rec -c bash C:/videos/`date +%Y-%m-%d-%H-%M-%S`.rec'

# Change all directories to 755 and non-executable files to 644 permissions
alias perms='find . -type d -print0 | xargs -0 chmod 755 && find . -type f ! -name "*.exe" ! -name "*.pyd" ! -name "*.dll" ! -name "*.DLL" ! -name "*.sh" -print0 | xargs -0 chmod 644'

# Use ack instead: curl http://betterthangrep.com/ack-standalone > /usr/bin
# alias ag='/usr/bin/ag "--ignore={.cache,node_modules,bower_components,*.csv,*.xls*}"'

# Python program aliases. Required because ActivePython doesn't parse cygwin paths
# alias o='python -ux C:/Apps/utils/o.cmd'
# alias publish='python C:/Apps/utils/publish.py'
alias builderrors='bash /code/cto/builderrors/builderrors'
alias vis='python C:/ext/vis/vis.py'
alias gramex0='python C:/ext/vis/gramex.py'
alias jsonpp='python -mjson.tool'
alias slides='python C:/site/gramener.com/viz/shows/slides.py'
alias slidetext='python C:/site/gramener.com/viz/shows/slidetext.py'
alias mail='python C:/site/gramener.com/viz/mail/mail/mail.py'
# alias R='R --no-save'

alias pdftotext='/c/Apps/xpdf/pdftotext'
alias 7z='/c/Program\ Files/7-Zip/7z.exe'
alias mysql='/c/Apps/xampp/mysql/bin/mysql -u root'
alias ab='/c/Apps/xampp/apache/bin/ab'
alias pngall='find -name "*.png" -print0 | xargs -0 -n 1 /c/Apps/utils/truepng -o max -cq'
alias paint='/c/Program\ Files/paint.net/PaintDotNet.exe'

# Download YouTube video
alias youtube-dl="yt-dlp"
# Download high-quality audio for music
alias youtube-audio='yt-dlp --extract-audio --audio-format opus --embed-thumbnail'
# Download compressed audio for speech-to-text
alias youtube-opus='yt-dlp --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'
# Download subtitles
youtube-subtitles () {
    curl -s "$(yt-dlp -q --skip-download --convert-subs srt --write-sub --sub-langs "en" --write-auto-sub --print "requested_subtitles.en.url" "$1")"
}

alias whisper="/c/Apps/whisper/faster-whisper-xxl --print_progress --output_dir source --batch_recursive --check_files --standard --output_format json srt --model medium --language en $FILE"

# alias pngmeta='/c/Apps/utils/truepng /zc9 /zm1-9 /zs0-3 /fe /a1 /i0'
# alias pngfast='find -name "*.png" -print0 | xargs -0 -n 1 /c/Apps/utils/truepng -o fast -i0 -a1 -cq -md remove all'
# alias pdf2svg='/c/Apps/pdf2svg/pdf2svg.exe'
# alias mongod='/c/Apps/MongoDB/bin/mongod.exe --dbpath=C:/Apps/MongoDB/data/'
# alias mysql2csv='/c/Apps/xampp/mysql/bin/mysqldump -u root --fields-terminated-by="," --fields-enclosed-by="\"" --lines-terminated-by="\n" --tab="."'
# alias mysqldump='/c/Apps/xampp/mysql/bin/mysqldump'
# alias elasticsearch='/c/Apps/elasticsearch/bin/elasticsearch.bat'
# alias gh='/c/Program\ Files/Github\ CLI/gh'
# alias rg='uvx --from ripgrep rg'

# Run deno with full permissions
alias denoall='deno --allow-all'

# PostgreSQL
# Use "C:\Apps\PostgreSQL\12\pgAdmin 4\bin\pgAdmin4.exe"

# Find files with Windows line endings
# alias winline="grep -IUlr --color $'\r'"

# Sort all files under subfolders by date
# alias latest='find -type f -printf "%T+ %p\n" | sort'

# netsh wlan set hostednetwork mode=allow ssid=Obisidian key=12345678
# You can access this machine at the same IP as the gateway IP
# alias wifistart='netsh wlan start hostednetwork'
# alias wifistop='netsh wlan stop hostednetwork'
# alias wlan=wifi

# Battery and system info
# alias batteryreport='powercfg /batteryreport'

# Start / stop service
# alias apachestart='net start "Apache2.4"'
# alias apachestop='net stop "Apache2.4"'
# alias httpd='/c/Apps/xampp/apache/bin/httpd.exe'

# Find duplicate files
alias duplicate='find -not -empty -type f -printf "%s\n" | sort -rn | uniq -d | xargs -I{} -n1 find -type f -size {}c -print0 | xargs -0 md5sum | sort | uniq -w32 --all-repeated=separate'

case "$(uname -s)" in
    CYGWIN*|MINGW32_NT*)
        set -o igncr # Ignore CR at the end of lines. Treat CRLF as LF
        alias g='cygstart'
        # npx script in Node 16 uses set -o igncr (good) but only in line 5.
        # Lines 2-4 have newlines and they fail. So use the CMD directly instead.
        alias npx='npx.cmd'
        # VS Code adds itself to the PATH. There, `code` is a shell script that doesn't work.
        ed () {
            code "`cygpath -aw \"$@\"`"
        }
        cursor () {
            cursor.cmd "`cygpath -aw \"$@\"`"
        }
        windiff () {
            code.cmd --diff "`cygpath -aw \"$1\"`" "`cygpath -aw \"$2\"`"
        }
        d () {
            cd "`cygpath -aw \"$1\"`"
        }
        ;;
    Linux)
        alias g='cmd.exe /C start'
        alias ed='code'
        alias windiff='code --diff'
        ;;
esac

png () {
    for file in $@; do
        /c/Apps/utils/truepng -o max -cq "$file"
    done
}
transparent () {
    convert $1 -fuzz 20% -transparent white transparent.$1
}

# Make and change into directory
mcd () {
    mkdir "$1"
    cd "$1"
}

# Convert newlines to spaces. Typical usage:
#   git add `k <<EOF
#   (paste the newly added files)
#   EOF`
k () {
    sed ':a;N;$!ba;s/\n/ /g' $1
}

alarm () {
    # Avoid printing "Done" by running in a subshell
    # https://stackoverflow.com/a/7687722/100904
    (python "C:/Apps/utils/alarm.py" $@ &)
}

grepfile () {
    cat "$1" | tr '\n' '\0' | xargs -0 grep "$2"
}

# Find unused images or Markdown files in *.md
unused () {
    find . -maxdepth 2 \( -name '*.md' -o -name '*.jpg' -o -name '*.png' -o -name '*.gif' -o -name '*.pdf' \) | sed 's/^\.\///' > /tmp/unused
    for p in $(cat /tmp/unused); do
        grep $p *.md > /dev/null || echo $p;
    done
    rm /tmp/unused
}

# Pad or buffer a file with spaces at the end
addspace() {
    local n="$1"
    shift
    for file in "$@"; do
        printf '%*s' "$n" "" >> "$file"
    done
}

# FFmpeg convert video to audio.
#   -b:a    audio bitrate
#   -ar     sample rate
audio () {
    /c/Apps/utils/ffmpeg.exe -i "$1" -b:a 32k -ac 1 -ar 22050 "$1.mp3"
}
opus () {
    /c/Apps/utils/ffmpeg.exe -i "$1" -c:a libopus -b:a 16k -ac 1 -application voip -vbr on -compression_level 10 "$1.opus"
}
avif () {
    /c/Apps/utils/ffmpeg.exe -i "$1" -b:v 0 -c:v libaom-av1 -crf 30 -tiles 2x2 -an "$1.avif"
}
# https://trac.ffmpeg.org/wiki/Encode/MP3
mp3 () {
    /c/Apps/utils/ffmpeg.exe -i "$1" -codec:a libmp3lame -q:a 2 "$1.mp3"
}
webpall () {
    for file in *.png; do
        /c/Apps/libwebp/bin/cwebp -short -lossless -o "${file%.png}.webp" "$file"
    done
}

keyframes () {
    filename="${1%.*}"
    # Select all keyframes ensuring a max gap of 1 second. Fit to a 512x512 bounding box. Compress JPEG. Don't reduce quality (no-benefit)
    # ffmpeg -i "$1" -vf "select='key+isnan(prev_selected_t)+gte(t-prev_selected_t\,1)',showinfo,scale='if(gt(a,1),512,-2)':'if(gt(a,1),-2,512)'" -vsync vfr -compression_level 10 "$filename-%03d.jpg" 2>&1 | grep 'pts_time' | sed 's/.*pts_time:\([0-9.]*\).*/\1/' > "$filename-timestamps.txt"
    ffmpeg -i "$1" -vf "select='key',showinfo,scale='if(gt(a,1),512,-2)':'if(gt(a,1),-2,512)'" -vsync vfr -compression_level 10 "$filename-%03d.jpg" 2>&1 | grep 'pts_time' | sed 's/.*pts_time:\([0-9.]*\).*/\1/' > "$filename-timestamps.txt"
}

# TODO: document -ss, -t for cropping

# To convert movies that don't have the right audio on Appa's Videocon TV:
#   AC3 audio encoding does not play. AAC does. Run:
#       ffprobe file 2>&1 | grep Stream
#   To convert, use: https://superuser.com/a/1237993
#       ffmpeg -i input.mkv -c copy -map 0:v:0 -map 0:a:0 -c:a:0 aac -b:a:0 320k -map 0:s? output.mkv
#   Speed: 30x. A 2.5 hr movie takes 5 minutes to convert.
audioformat () {
    for i in *
    do
        echo "$i"
        ffprobe "$i" 2>&1 | grep Stream
    done
}

# Project lines of code
loc() {
    git clone "git@code.gramener.com:$1/$2"
    cd $2
    # Check out branch as of time https://stackoverflow.com/a/6990682/100904
    git checkout `git rev-list --all -n 1 --first-parent --before="2020-04-01 00:00"`
    find . -name '*.py' -print0 | xargs -0 wc -l | tail -1
    find . -name '*.js' -print0 | xargs -0 wc -l | tail -1
    git checkout `git rev-list --all -n 1 --first-parent --before="2020-05-01 00:00"`
    find . -name '*.py' -print0 | xargs -0 wc -l | tail -1
    find . -name '*.js' -print0 | xargs -0 wc -l | tail -1
    cd ..
}

# Synchonization commands
sync_rclone() {
    rclone --drive-root-folder-id 13QYzZtR9urUvAcjpfurk5v78M1YK3Plr sync gstraive: C:/data/barry-callebaut-hackathon
    rclone --drive-root-folder-id 0AGdBEInQk0kRUk9PVA sync gstraive: C:/data/gramener-capitalization
    # rclone --drive-root-folder-id 1Tpb_1Z4KufFpD2Rl0UyPIyQlHzluXxbC sync gstraive: C:/data/2024-11-14-straive-board-meeting
}

sync_onedrive() {
    rsync -avzP /c/Gramener/Gramener\ Team\ -\ Documents/General/Marketing/demos.xlsx ubuntu@gramener.com:/mnt/gramener/onedrive/gramener-team/General/Marketing/
    rsync -avzP /c/Gramener/Gramener\ Team\ -\ Documents/General/Skills/*.xlsx ubuntu@gramener.com:/mnt/gramener/onedrive/gramener-team/General/Skills/
}

# Run rsync ignoring .gitignore and setting all file permissions to 644 and directories to 755
sync_straive() {
    rsync -avzP --exclude='.git' --filter=':- .gitignore' --chmod=D755,F644 ~/code/$1 root@straive.app:/var/www/
}

sync_demos() {
    rsync -avzP --exclude='.git' --filter=':- .gitignore' --chmod=D755,F644 /c/Dropbox/data/learn.gramener.com/demos.xlsx ubuntu@gramener.com:/mnt/gramener/onedrive/gramener-team/General/Marketing/
}


# RSync notes to learn.gramener.com/wiki/* -- these are files I don't want to commit
sync_wiki() {
    rsync -avzP --exclude='README.md' --chmod=D755,F644 /c/Dropbox/notes/learnwiki/*.md ubuntu@gramener.com:/mnt/gramener/apps/learn.gramener.com.v1/_wiki/
}

# Sync gists to github/gists
sync_gists() {
  # Directory to sync gists
  BASE_DIR="/github/gists"

  # Ensure the base directory exists
  mkdir -p "$BASE_DIR"

  if [ $# -eq 0 ]; then
    # List all gists and process each line
    gh gist list --limit 1000 | cut -f1,2 | while IFS=$'\t' read -r gist_id gist_desc; do
        # Create a slug by replacing invalid filename characters with hyphens and converting to lowercase, limiting to 64 characters
        slug=$(echo "$gist_desc" | tr -c '[:alnum:]' '-' | tr '[:upper:]' '[:lower:]' | cut -c1-64)

        # Set the gist directory
        gist_dir="$BASE_DIR/$slug"

        # Clone or pull the gist
        if [ ! -d "$gist_dir" ]; then
        echo "Cloning $gist_dir..."
        gh gist clone "$gist_id" "$gist_dir"
        else
        echo "Pulling $gist_dir..."
        (cd "$gist_dir" && git pull -q)
        fi
    done
  else
    # Find and sync matching directories
    for pattern in "$@"; do
      find "$BASE_DIR" -maxdepth 1 -type d -name "*$pattern*" | while read gist_dir; do
        if [ "$gist_dir" != "$BASE_DIR" ]; then
          echo "Pulling $gist_dir..."
          (cd "$gist_dir" && git pull -q)
        fi
      done
    done
  fi
}

# Pad PDF files to a minimum target size by appending whitespace
# Usage: padpdf file1.pdf file2.pdf ...
padpdf() {
  # Target file size in bytes (5MB)
  target=5000000
  # Size increment for padding (200KB)
  increment=200000

  # Process each PDF file passed as argument
  for file in "$@"; do
    # If the file is not a a .PDF (or .pdf, or a PDF spelt in any case), convert it to PDF
    if [[ "$file" != *.pdf && "$file" != *.PDF ]]; then
      pdf="${file%.*}.pdf"
      echo "Converting '$file' to '$pdf'..."
      magick "$file" "$pdf"
    else
      pdf="$file"
    fi

    # Get current file size in bytes using stat
    # -c%s: custom format that returns only the size in bytes
    filesize=$(stat -c%s "$pdf")

    # Only pad if file is smaller than target size
    if (( filesize < target )); then
      # Calculate how many MB of padding needed
      # Integer division ensures we don't exceed target
      add_mb=$(( (target - filesize) / increment ))
      bytes_to_add=$(( add_mb * increment ))

      # Only append if we need to add bytes
      if (( bytes_to_add > 0 )); then
        # printf with format '%*s':
        # %*s - creates a string of spaces:
        #   * takes width from first argument (bytes_to_add)
        #   s prints second argument ("" - empty string)
        # >> appends the spaces to the PDF file
        printf '%*s' "$bytes_to_add" "" >> "$pdf"
      fi
    fi
  done
}

receipts() {
  # cd "/cygdrive/i/My Drive/receipts"

  shopt -s nullglob nocaseglob
  target=5000000
  increment=1000000

  for file in *.jpg *.jpeg; do
    pdf="${file%.*}.pdf"
    if [[ ! -e "$pdf" ]]; then
      echo "Converting '$file' to '$pdf'..."
      magick "$file" "$pdf"

      # For Linux: stat -c%s; for macOS: stat -f%z "$pdf"
      filesize=$(stat -c%s "$pdf")
      if (( filesize < target )); then
        add_mb=$(( (target - filesize) / increment ))
        bytes_to_add=$(( add_mb * increment ))
        if (( bytes_to_add > 0 )); then
          printf '%*s' "$bytes_to_add" "" >> "$pdf"
        fi
      fi
    fi
  done
}

# Usage: pdf_decrypt file.pdf password
pdf_decrypt() {
    uv run --with pikepdf python -c 'import pikepdf, sys; pdf = pikepdf.open(sys.argv[1], password=sys.argv[2], allow_overwriting_input=True); pdf.save()' "$1" "$2"
}

# If a command is not found, try it with npx
# https://www.npmjs.com/package/npx#shell-auto-fallback
command_not_found_handle() {
    # Do not run within a pipe
    if test ! -t 1; then
        >&2 echo "command not found: $1"
        return 127
    fi
    if which npx > /dev/null; then
        echo "$1 not found. Trying with npx..." >&2
    else
        return 127
    fi
    if ! [[ $1 =~ @ ]]; then
        npx --no-install "$@"
    else
        npx "$@"
    fi
    return $?
}

# Notes
#
# tmux attach
# tmux new-window
# tmux rename-window
# tmux split-window -h
# ^bc to create new screen
# ^bo to switch panes
# ^bn for next pane
# ^b1 for 1st
# ^bd to detach session (tmux attach can re-attach)
# ^b[ to enter scroll mode (use arrow keys to up/down). Then ^c to end
