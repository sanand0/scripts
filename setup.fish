# Main fish configuration file

# https://mise.jdx.dev/getting-started.html
# Install mise via `curl https://mise.run | sh`
$HOME/.local/bin/mise activate fish | source

# Skip fish greeting
set -g fish_greeting ""

# Migrate setup from ~/.config/fish/config.fish
set -gx PATH $PATH $HOME/.lmstudio/bin

# Add scripts to PATH
set -gx PATH $PATH $HOME/code/scripts
# Some of my scripts are still on Dropbox. TODO: Migrate them
set -gx PATH $PATH $HOME/Dropbox/scripts

# For each .venv/bin in $HOME/apps/*, add to PATH
for app in $HOME/apps/*
    if test -d "$app/.venv/bin"
        set -gx PATH $PATH "$app/.venv/bin"
    end
end

# Source global uv environment
source $HOME/apps/global/.venv/bin/activate.fish

# unset for fish
abbr unset 'set --erase'

# uv configuration to allow Codex, etc. to use uv
export UV_TOOL_DIR="$HOME/.local/share/uv/tools"
export UV_CACHE_DIR="$HOME/.cache/uv"
export XDG_DATA_HOME="$HOME/.local/share"

# fx environment variables. https://fx.wtf/configuration
export FX_LINE_NUMBERS=true
export FX_SHOW_SIZE=true

# Via Google Cloud SDK.
if [ -f '/home/sanand/google-cloud-sdk/path.fish.inc' ]; . '/home/sanand/google-cloud-sdk/path.fish.inc'; end

# less should color files
export LESS='-R'
# export LESSOPEN='|pygmentize -g -O style=github-dark %s'

# grep should color files
export GREP_OPTIONS='--color=auto'

# Set up fzf
export FZF_DEFAULT_COMMAND='fd --type f --follow --exclude node_modules --strip-cwd-prefix'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_DEFAULT_OPTS='--layout=reverse --preview "bat --style=numbers --color=always --line-range :500 {}"'

# Basic commands and aliases
# -----------------------------------------------

# git mis-spellings
abbr --add gt   git
abbr --add gi   git
abbr --add it   git
abbr --add gitt git
abbr --add giit git

# Faster, better grep
abbr --add grep ug
abbr --add search ug -i --smart-case --bool -Q

# Faster, better less
abbr --add less bat

# Better curl
abbr --add http 'uvx httpie'

# Better ncdu
abbr --add ncdu gdu

# Bandwhich requires sudo and is behind mise, so use full path
abbr --add bandwhich 'sudo $(which bandwhich)'

# Command line Excel. For more formats, see https://www.visidata.org/docs/formats/
abbr --add vd 'uvx --from visidata --with openpyxl vd'
abbr --add visidata 'uvx --from visidata --with openpyxl vd'

# ePub Reader
abbr --add epr 'uvx --from epr-reader epr'

# Local tunnel - ngrok alternative
abbr --add tunnelmole 'npx -y tunnelmole'
abbr --add localtunnel 'npx -y localtunnel'

# Kill process by name, port and/or number (e.g. fkill :8000)
abbr --add fkill 'npx -y fkill-cli fkill'

# Search
abbr --add google 'mise x ubi:zquestz/s -- s -p google'

# GMail command line
export PAGER='bat'      # Required for cmdg
export EDITOR='fresh'   # Required for cmdg. Alternative to micro
abbr --add mail cmdg

# Allow delta to override the default PAGER (e.g. bat) which interferes with its output
export DELTA_PAGER='less -R'

# Google Calendar command line
abbr --add gcalcli 'uvx gcalcli'
abbr --add agenda 'uvx gcalcli agenda --calendar $EMAIL --nodeclined $(date -Ihours) (date -I --date "+2 days")'

# Color diffs
abbr --add icdiff 'uvx --offline icdiff'

# Jupyter Lab
abbr --add jupyter-lab 'uvx --offline --from jupyterlab jupyter-lab'

# Convert PDF to text
abbr --add pdftotext 'PYTHONUTF8=1 uvx --with markitdown[pdf] markitdown'

# MP3tag alternative
abbr --add mp3tag puddletag

# Run Python debugger on error
abbr --add uvd 'PYTHONPATH=~/code/scripts/pdbhook uv'

# Recent blog posts
abbr --add recentblogs 'rg -l "^[[:space:]]*- llms" -g ~/code/blog/posts/**/*.md | xargs rg "^date:" | sort -k2 -r | head -n 30 | cut -d: -f1 | xargs uvx files-to-prompt --cxml'

# File sync utilities
# -----------------------------------------------

# Create new bucket at https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/r2/overview
# View all files via `rclone tree r2:`

# Common rclone bisync (two-way sync) options - optimized for speed
# Add --resync for the first time to MERGE
export _RCLONE_BISYNC_OPTIONS='--create-empty-src-dirs --slow-hash-sync-only --fast-list --size-only --checkers 16 --transfers 8 --resilient --metadata --fix-case --verbose --progress'

# Sync work files to Google drive
abbr --add straivesync rclone bisync ~/Documents/straive gdrive-straive:straive $_RCLONE_BISYNC_OPTIONS
abbr --add meetsync    'rclone bisync ~/Documents/Meet\ Recordings gdrive-straive:Meet\ Recordings' $_RCLONE_BISYNC_OPTIONS
abbr --add demosync    rclone bisync ~/Documents/straive-demos straive-demos:straive-demos $_RCLONE_BISYNC_OPTIONS

# private bucket is deployed at https://private.s-anand.net/ and is shared with colleagues
abbr --add privatesync rclone bisync ~/r2/private r2:private $_RCLONE_BISYNC_OPTIONS
# files bucket is deployed at https://files.s-anand.net/ and is public - typically assets linked from my blog
abbr --add filessync   rclone bisync ~/r2/files r2:files $_RCLONE_BISYNC_OPTIONS

# Back up files to Hetzner Storage Box. See ~/.ssh/config for hetzner host config.
# Set up SSH key via https://docs.hetzner.com/storage/storage-box/backup-space-ssh-keys
abbr --add hetznerbackup rsync -avzP \
  ~/Documents/audio \
  ~/Documents/bcg \
  ~/Documents/books \
  ~/Documents/calls \
  ~/Documents/comics \
  ~/Documents/gitlab \
  ~/Documents/infy \
  ~/Documents/screenplays \
  ~/Documents/talks \
  ~/Pictures \
  hetzner:/home/

# Clipboard Utilities
# -----------------------------------------------

# Convert unicode characters to ASCII. Useful to strip em-dashes, smart quotes, etc. from ChatGPT
abbr --add ascii 'xclip -selection clipboard -o | uv run --with anyascii python -c "import sys, anyascii; sys.stdout.write(anyascii.anyascii(sys.stdin.read()))" | xclip -selection clipboard'

# Convert unicode characters to ASCII. Useful to strip em-dashes, smart quotes, etc. from ChatGPT
abbr --add striplinks 'xclip -selection clipboard -o | uv run ~/code/scripts/striplinks.py | xclip -selection clipboard'
abbr --add stripdetails 'xclip -selection clipboard -o | uv run ~/code/scripts/striptags.py details | xclip -selection clipboard'

# Copy to clipboard. Typical usage: command | clip
abbr --add clip 'xclip -selection clipboard'

# Convert clipboard to Markdown rich text. Useful to copy Markdown and paste into GMail.
abbr --add md2rtf 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript+hard_line_breaks -t html --syntax-highlighting=none --wrap=none | xclip -sel clip -t text/html -i'

# Convert clipboard to Markdown HTML. Useful to copy Markdown and paste into code.
abbr --add md2html 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript+hard_line_breaks -t html --syntax-highlighting=none --wrap=none | xclip -sel clip -i'

# LLM Utilities
# -----------------------------------------------

abbr --add claude-yolo 'npx -y @anthropic-ai/claude-code --dangerously-skip-permissions'
abbr --add copilot 'npx -y @github/copilot'
abbr --add opencode 'npx -y opencode-ai'

function secret --description "Extract secret from .env"
    awk -F= -v k="$argv[1]" '$1==k{print substr($0,index($0,"=")+1);exit}' $HOME/Dropbox/scripts/.env | string trim -c '"'
    # Slower version using python-dotenv
    # dotenv -f $HOME/Dropbox/scripts/.env get $argv[1]
end

# SaaS utilities
# -----------------------------------------------
abbr --add hs 'npx -y --package @hubspot/cli hs'

# File Utilities
# -----------------------------------------------

# rm moves to trash
abbr --add rm trash

# List files, sorted by time, with git status and relative time
function l
    eza -l -snew --git --time-style relative --no-user --no-permissions --color-scale=size --icons=auto $argv
end

# Life Lessons from the top 200 lines of 5 / 20 recent random notes
abbr --add lesson 'find ~/Dropbox/notes -type f -printf "%T@ %p\n" \
    | sort -nr \
    | head -n 20 \
    | cut -d" " -f2- \
    | shuf \
    | head -n 5 \
    | xargs -I {} head -n 200 "{}" \
    | llm -s "Pick 3 non-obvious life lessons. Cite filenames"
'

# Make and change directory
function mcd --description "mkdir DIR && cd DIR"
    mkdir -p -- $argv[1]
    and cd -- $argv[1]
end

# Bug fixes
# -----------------------------------------------

# Toggle GNOME extension to restart it after screen blank
# https://claude.ai/chat/9f993bc0-ba50-46e0-b0d5-38a77c0b8621
abbr --add dock 'gsettings set org.gnome.shell disable-user-extensions true; gsettings set org.gnome.shell disable-user-extensions false'

# Audio/video
# ----------------------------------------------

# Audio record only
# Stats
#   -hide_banner                 # Removes long build/config header
#   -stats                       # Show size=... time=... bitrate=... speed=...
#   -v warning                   # Only warnings and above. use -v error for quieter
# Channels (-f pulse -i)
#   default                                                 # PulseAudio's "default" source-your microphone input via the default sink-source loopback
#   alsa_output.pci-0000_00_1f.3.analog-stereo.monitor      # The monitor of your stereo output ("what-you-hear") created by PulseAudio for speaker capture
# Mixing & per-source processing (-filter_complex)
#   [0:a]highpass=f=100,lowpass=f=12000,afftdn=nf=-30,volume=4[m]
#     highpass=f=100             # Cuts frequencies below 100 Hz to remove rumble and handling noise
#     lowpass=f=12000            # Attenuates above 12 kHz to reduce hiss and harshness
#     afftdn=nf=-30              # FFT denoiser with noise floor at -30 dB (-20 dB = stronger NR; -40 dB = gentler)
#     volume=2                   # dB boost on the mic path before mixing (+3 dB per volume level)
#     [m]                        # Labels this processed mic stream as "[m]"
#   [1:a]pan=mono|c0=FR[s]       # Collapses speaker stream to mono, maps it to the Front Right channel, labels "[s]" (pan filter)
#   [m][s]amerge, loudnorm=I=-16:LRA=7:tp=-1[a]
#     amerge                     # Merges the two mono inputs ("m"=L, "s"=R) into a single stereo stream
#     loudnorm=I=-16:LRA=7:tp=-1 # EBU R128 loudness normalization (Integrated -16 LUFS; Loudness Range 7; True-Peak ceiling -1 dBTP)
#     [a]                        # Labels the final processed stream as "[a]"
# Output mapping & encoding
#   -map "[a]"                   # Selects the filtered audio "[a]" for output
#   -ar 48000                    # Resamples to 48 kHz (Opus native rate) for optimal quality
#   -ac 2                        # Forces 2 output channels (L/R stereo)
#   -c:a libopus                 # Uses FFmpeg's libopus encoder for Opus audio
#   -b:a 24k                     # Sets bitrate to 24 kb/s for voice quality recording
function record --description "record audio from mic + speakers into ~/Documents/calls"
  read -l -P "Use HEADSET to avoid echo. ENTER starts, Ctrl+C cancels: "
  or return
  # Optional output filename; default to timestamped path
  if test (count $argv) -gt 0
    set out "$argv[1..]"
  else
    set out record-$(date "+%Y-%m-%d-%H-%M-%S")
  end
  ffmpeg -hide_banner -stats -v error \
  -f pulse -i default \
  -f pulse -i alsa_output.pci-0000_00_1f.3.analog-stereo.monitor \
  -filter_complex "\
    [0:a]highpass=f=100,lowpass=f=12000,afftdn=nf=-30,volume=2[m]; \
    [1:a]pan=mono|c0=FR[s]; \
    [m][s]amerge, loudnorm=I=-16:LRA=7:tp=-1[a]" \
  -map "[a]" \
  -ar 48000 \
  -ac 2 \
  -c:a libopus \
  -b:a 24k \
  "$HOME/Documents/calls/$out.opus"
end

# Screen record only
# Channels & source (-f x11grab -i)
#   -f x11grab                         # Captures your X11 screen
#   -video_size 1920x1080              # Sets recording resolution
#   -framerate 5                       # Low frame rate to minimize CPU
#   -i $DISPLAY+0,0                    # Uses current DISPLAY at offset 0,0
# Hardware-accelerated processing (-vf, -c:v)
#   format=nv12                        # Converts to NV12 pixel format for VAAPI
#   hwupload                           # Uploads frames to GPU memory
#   -c:v h264_vaapi                    # Encodes via VAAPI (Intel/AMD GPU)
#   -qp 20                             # Quality parameter (20→visually lossless)
# Output
#   ~/Downloads/screenrecord-<timestamp>.mp4
abbr --add screenrecord 'ffmpeg -hide_banner -stats -v warning \
    -vaapi_device /dev/dri/renderD128 \
    -f x11grab \
    -video_size 1920x1080 \
    -framerate 5 \
    -i $DISPLAY+0,0 \
    -vf 'format=nv12,hwupload' \
    -c:v h264_vaapi \
    -qp 20 \
    ~/Downloads/screenrecord-$(date "+%Y-%m-%d-%H-%M-%S").mp4'

# Screen + audio recording.
# Includes options from record and screenrecord above, plus a `-map 2:v`
abbr --add videorecord '
  read -l message -P "Use a headset to avoid echo. Press ENTER."; \
  ffmpeg -hide_banner -stats -v warning \
    -vaapi_device /dev/dri/renderD128 \
    -f pulse -i default \
    -f pulse -i alsa_output.pci-0000_00_1f.3.analog-stereo.monitor \
    -f x11grab \
    -video_size 1920x1200 \
    -framerate 5 \
    -i $DISPLAY+0,0 \
    -filter_complex "\
      [0:a]highpass=f=100,lowpass=f=12000,afftdn=nf=-30,volume=7[m]; \
      [1:a]pan=mono|c0=FR[s]; \
      [m][s]amerge,loudnorm=I=-16:LRA=7:tp=-1[a]" \
    -map 2:v \
    -map "[a]" \
    -vf "format=nv12,hwupload" \
    -c:v h264_vaapi \
    -qp 20 \
    -ar 48000 \
    -ac 2 \
    -c:a libopus \
    -b:a 24k \
    ~/Downloads/videorecord-(date "+%Y-%m-%d-%H-%M-%S").mkv'

abbr --add youtube-dl 'uvx --with mutagen yt-dlp --remote-components ejs:github'
abbr --add youtube-opus 'uvx --with mutagen yt-dlp --remote-components ejs:github --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "FFmpegAudioConvertor:-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'
abbr --add youtube-audio 'uvx --with mutagen yt-dlp --remote-components ejs:github --extract-audio --audio-format opus --embed-thumbnail'
abbr --add youtube-mp3 'uvx --with mutagen yt-dlp --remote-components ejs:github --extract-audio --audio-format mp3 --audio-quality 5'
abbr --add yt-dlp 'uvx --with mutagen yt-dlp --remote-components ejs:github'

abbr --add shorten 'llm --system "Suggest 5 alternatives that a VERY concise, with fewer words"'
abbr --add transcribe 'llm -m gemini-2.5-flash -s "Transcribe. Drop um, uh, etc. for smooth speech. Make MINIMAL corrections. Break into logical paragraphs. Begin each paragraph with a timestamp. Format as Markdown. Use *emphasis* or **bold** for key points. Prefix audience questions with Question: ... and answers with Answer: ..." -a'
abbr --add unbrace 'npx -y jscodeshift -t $HOME/code/scripts/unbrace.js'

function avif --description "avif file1.jpg file2.png ... converts into file1.avif file2.avif (1920x1080 max)"
    for file in $argv
        ffmpeg -i $file -vf "scale=w=1920:h=1080:force_original_aspect_ratio=decrease,format=yuv420p" -f yuv4mpegpipe - \
        | avifenc -q 50 --speed 4 --jobs $(nproc) -a tune=ssim --stdin (string replace -r '\.[^.]+$' '.avif' $file)
    end
end

function webp-lossy --description "webp-lossy file1.jpg file2.png ... converts into file1.webp file2.webp with lossy compression"
    for file in $argv
        cwebp -q 10 -m 6 $file -o (string replace -r '\.[^.]+$' '.webp' $file)
    end
end

function webp-lossless --description "Convert images to compact lossless WebP with optional resizing and color quantization"
    # 1. Define the options spec
    # 'c/colors=' : -c or --colors, requires a value (=)
    # 's/size='   : -s or --size, requires a value (=)
    # 'h/help'    : -h or --help, generic switch
    argparse 'c/colors=!_validate_int' 's/size=!_validate_int' 'h/help' -- $argv
    or return

    if set -q _flag_help
        echo "Usage: webp-lossless [-c|--colors N] [-s|--size N] file1 [file2 ...]"
        return 0
    end

    # 2. Set defaults if flags weren't provided
    set -l colors 8
    set -l resize_opts ""

    if set -q _flag_colors
        set colors $_flag_colors
    end

    if set -q _flag_size
        set resize_opts "-resize" "$_flag_size"x"$_flag_size"
    end

    # 3. Process files (argparse removes flags from $argv, leaving only files)
    for file in $argv
        set -l output (string replace -r '\.[^.]+$' '.webp' -- $file)

        echo "Processing $file -> $output (Colors: $colors, Resize: $_flag_size)..."

        # Pipeline:
        # magick: reads input -> optional resize -> outputs PNG to stdout
        # pngquant: quantizes to $colors -> no dithering -> strip metadata -> max speed -> reads from stdin
        # cwebp: lossless -> max compression (-z 9) -> multi-threaded -> reads from stdin
        magick "$file" $resize_opts png:- | \
        pngquant $colors --nofs --strip --speed 1 - | \
        cwebp -quiet -lossless -z 9 -mt -o "$output" -- -
    end
end

# Compress screen casts. https://chatgpt.com/c/69a236ec-b8bc-839e-a58a-d4c78ccf9518
# Increase quality with lower crf= (55 is poor, 45 is good) and higher fps= (3 is small, 6 is good).
#   screencastcompress demo.webm
#   screencastcompress --crf 45 --fps 6 demo.webm talk.webm
function screencastcompress --description "Compress screen casts. Usage: screencastcompress [--crf N] [--fps N] input1.webm [input2.webm ...]"
    argparse 'c/crf=!_validate_int' 'f/fps=!_validate_int' 'h/help' -- $argv
    or return

    if set -q _flag_help
        echo "Usage: screencastcompress [--crf N] [--fps N] input1.webm [input2.webm ...]"
        return 0
    end

    if test (count $argv) -lt 1
        echo "Usage: screencastcompress [--crf N] [--fps N] input1.webm [input2.webm ...]"
        return 1
    end

    set -l crf 55
    set -l fps 5

    if set -q _flag_crf
        set crf $_flag_crf
    end

    if set -q _flag_fps
        set fps $_flag_fps
    end

    for input in $argv
        set -l output (string replace -r -- '\.[^.]+$' "-crf"$crf"-fps"$fps".webm" "$input")
        ffmpeg -hide_banner -stats -v warning -i "$input" -vf "crop=iw-mod(iw\,2):ih-mod(ih\,2),fps=$fps" -c:v libsvtav1 -preset 8 -crf $crf -pix_fmt yuv420p -an "$output"
    end
end

# Usage: pdf_decrypt file.pdf password. Also: pdfcpu decrypt -upw password input.pdf output.pdf
abbr --add pdf_decrypt "uv run --with pikepdf python -c 'import pikepdf, sys; pdf = pikepdf.open(sys.argv[1], password=sys.argv[2], allow_overwriting_input=True); pdf.save()'"

function asciirec --description "Record terminal session with asciinema"
    set -l ts (date "+%Y-%m-%d-%H-%M-%S")
    uvx --offline asciinema rec -c bash ~/Videos/$ts.rec
end

function mcd --description "mkdir DIR && cd DIR"
    mkdir -p -- $argv[1]
    and cd -- $argv[1]
end

# mdq is an alternative
function mdgrep -d "Grep markdown by top-level bullet blocks"
    awk -v pat="$argv[1]" '
        /^[-*] [^ ]/ { if(b && m) print b; b=$0; m=0; next }
        { b=b ORS $0 }
        $0 ~ pat { m=1 }
        END { if(b && m) print b }
    ' $argv[2..-1]
end


function meeting --description "Create a new meeting transcript file"
    set date $(date -Idate)
    set title "$date $argv[1..]"
    set file "$HOME/Dropbox/notes/transcripts/$title.md"
    code $file
    if not test -e $file
        echo "---
tags:
goal:
kind candor:
effectiveness:
---

# $title

## Transcript
" > $file
    end
    # Also start an audio recording named after the meeting
    record "$title"
end

function blog --description "Create a new blog post"
    set date $(date -Iseconds)
    set title "$argv[1..]"
    set year (string sub -s 1 -l 4 $date)
    set slug (string replace -a ' ' '-' (string lower $title))
    set file "$HOME/code/blog/posts/$year/$slug.md"
    code $file
    if not test -e $file
        echo "---
title: $title
date: $date
categories:
    - links
---
" > $file
    end
end

# Like llm -e but with streaming.
function copycode --description 'Stream + copy last code fence. Usage: llm "Write Tetris in Python" | copycode'
    tee /dev/tty | awk 'BEGIN{f=0} /```/{f=!f; next} f{buf=buf$0"\n"} END{print buf}' | xclip -selection clipboard
end

function pasteit --description "Paste output into buffer. Usage: llm -t fish 'Largest file' | pasteit"
    read -l buf
    commandline -r -- $buf
    commandline -f repaint
end

function trimdiff --description 'git diff | trimdiff 100 2000 shows first/last 100 lines, max 2000 chars per line'
    set -l N $argv[1]; test -z "$N"; and set N 100
    set -l C $argv[2]; test -z "$C"; and set C 2000
    awk -v N="$N" -v MAXC="$C" '
      BEGIN { H = N+0 ? N : 100; T = H }
      function pr(s){ if(length(s)>MAXC) s=substr(s,1,MAXC-3)"..."; print s }
      function flush( trimmed,i ){
        if(!infile) return
        trimmed = total - head - tailn
        if(trimmed>0) pr("... (" trimmed " lines trimmed)")
        for(i = tailpos - tailn; i < tailpos; i++) pr(buf[i % T])
        infile = 0
      }
      /^diff --/ { flush(); infile=1; head=0; total=0; tailpos=0; tailn=0; pr($0); next }
      {
        if(!infile){ pr($0); next }
        total++
        if(head < H){ pr($0); head++ }
        else if(T>0){ buf[tailpos % T]=$0; tailpos++; if(tailn<T) tailn++ }
      }
      END { flush() }
    '
end

function livesync --description "Merge live branch into main (or specified) branch. Create new live branch."
    set -l branch $argv[1]
    test -z "$branch"; and set branch main

    git checkout $branch
    git merge --squash live
    # Use llm to generate message based on diffs. Max 300 lines of diff per file
    git diff --cached | trimdiff | llm --system (prompt git-commit | string collect) | git commit -F -
    git push
    git push origin --delete live
    git branch -D live
    git checkout -b live
    git push -u origin live
end

function pyrun --description "Write & run Python code to execute a task"
    # Join all arguments into one quoted prompt
    set query (string join ' ' $argv)

    llm "$query" --system '
Write minimal Python code inside ```python...```
Begin with inline script dependencies. Example:
# /// script
# requires-python = ">=3.13"
# dependencies = ["pandas", ...]
# ///
import pandas as pd
...' \
    | awk '
        { print > "/dev/stderr"; all = all $0 ORS }
        /^```/ { seen = 1; code = !code; next }
        code   { print; next }
        END    { if (!seen) print all }
      ' \
    | uv run -
end

function prompt --description "Example: llm --system \"(prompt core-concepts)\" Parenting"
    for dir in $HOME/code/prompts $HOME/code/scripts/agents/custom-prompts
        set file $dir/$argv[1].md
        if test -f $file
            awk '/^---$/ {count++; next} count >= 2' $file | string trim
            return
        end
    end
end

# This is a very useful function. Ask for a command on the CLI and you get it. Paste and run.
function with --description "Example: with gh,jq 'Find last 3 repos I committed to'"
    llm --system "Write JUST a fish command using $argv[1]" "$argv[2..]" -o reasoning_effort minimal \
    | tee /dev/tty \
    | awk '
        { all = all $0 ORS }                    # keep full text for fallback
        /```/ {                                 # fence line? Only emit first block
            if (!got) { f = !f; if (!f) got = 1 }
            next
        }
        f && !got { buf = buf $0 ORS }          # collect lines inside first block
        END { printf "%s", (got ? buf : all) }  # print first block if found, else full text
        ' \
    | xclip -selection clipboard
end

function aimode --description "Example: aimode 'What is AI?' opens Google AI Mode search"
    set -l query (string join " " $argv)
    set -l encoded (string escape --style=url $query)
    open "https://www.google.com/search?udm=50&q=$encoded"
end

function youtube-subtitles --description "downloads subtitles from YouTube video URL"
    curl -s "$(yt-dlp -q --skip-download --remote-components ejs:github --convert-subs srt --write-sub --sub-langs "en" --write-auto-sub --print "requested_subtitles.en.url" $argv[1])"
end

function opus --description "opus *.mp4 converts it to *.opus (voice quality)"
    for file in $argv
        ffmpeg -hide_banner -stats -v warning -i $file -c:a libopus -b:a 12k -ac 1 -application voip -vbr on -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $file)
    end
end

# -b:a 48k is OK for many tracks. 64k works for all on earphones. 80-96k for electronic/classical music
# -ac 2 is not required. Mono stays mono. 5.1 downmixes to 2 because Opus is max 2 channels
# -ar 48000 is Opus' native sampling rate
# -frame_duration 60 is more efficient for music than the default 20 or 40 ms
function opusmusic --description "opus *.mp4 converts it to *.opus (music quality)"
    for file in $argv
        ffmpeg -hide_banner -stats -v warning -i $file -c:a libopus -b:a 48k -application audio -frame_duration 60 -vbr on -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $file)
    end
end

function ffsplit --description "ffsplit 00:12:00 00:34:00 input.mp4"
    set in $argv[-1]
    set timestamps $argv[1..-2]
    set prev 0
    set i 1

    for ts in $timestamps
        # Use -ss before -i for fast/clean seeking
        # We calculate duration (-t) because -to behaves differently before -i
        ffmpeg -hide_banner -stats -v warning \
            -ss $prev -to $ts -i "$in" \
            -map 0 -c copy -avoid_negative_ts make_zero \
            (string replace -r -- '(\.[^.]+)$' "-$i\$1" "$in")

        set prev $ts
        set i (math $i + 1)
    end

    # Last segment
    ffmpeg -hide_banner -stats -v warning \
        -ss $prev -i "$in" \
        -map 0 -c copy -avoid_negative_ts make_zero \
        (string replace -r -- '(\.[^.]+)$' "-$i\$1" "$in")
end

# whisper --output_format txt $inputfile
function whisper --description "transcribe audio file using Whisper Ctranslate2"
    source $HOME/apps/whisper-ctranslate2/.venv/bin/activate.fish
    export LD_LIBRARY_PATH="/home/sanand/apps/whisper-ctranslate2/.venv/lib64/python3.11/site-packages/nvidia/cublas/lib/:/home/sanand/apps/whisper-ctranslate2/.venv/lib64/python3.11/site-packages/nvidia/cudnn/lib/"
    whisper-ctranslate2 --device cuda --language en $argv[1..]
    deactivate
end

# webm-compress $input $width $frame_samples $output
function webm-compress --description "webm-compress input.webm 500 (width) 8 (sampling) output.webm"
    set in $argv[1]
    set --default width $argv[2] 500
    set --default sampling $argv[4] 1
    set --default out $argv[4] (string replace '.webm' '.compressed.webm' $in)
    ffmpeg -hide_banner -stats -v warning -i $in \
        -filter_complex "select='not(mod(n\,$sampling))',scale=$width:-1" \
        -c:v libvpx-vp9 -b:v 0 -crf 40 \
        $out
end

# https://yazi-rs.github.io/docs/quick-start
function y
    set tmp (mktemp -t "yazi-cwd.XXXXXX")
    yazi $argv --cwd-file="$tmp"
    if read -z cwd < "$tmp"; and [ -n "$cwd" ]; and [ "$cwd" != "$PWD" ]
        builtin cd -- "$cwd"
    end
    rm -f -- "$tmp"
end

# Completions
# -----------------------------------------------

# https://github.com/cantino/mcfly
mcfly init fish | source

# https://github.com/openai/codex/blob/main/docs/getting-started.md#shell-completions
codex completion fish | source

# https://github.com/iffse/pay-respects
pay-respects fish --alias | source

type -q fzf; and fzf --fish | source
type -q zoxide; and zoxide init fish | source
type -q starship; and starship init fish | source

# I store secrets in a .env file. But it's unsafe to source them in every shell. #TODO Use direnv
# source "/c/Dropbox/scripts/.env"
