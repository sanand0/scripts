# Main fish configuration file

# https://mise.jdx.dev/getting-started.html
# Install mise via `curl https://mise.run | sh`
$HOME/.local/bin/mise activate fish | source

# Migrate setup from ~/.config/fish/config.fish
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

# less should color files
export LESS='-R'
export LESSOPEN='|pygmentize -g -O style=github-dark %s'

# grep should color files
export GREP_OPTIONS='--color=auto'

# Set up fzf
export FZF_DEFAULT_COMMAND='fd --type f --follow --exclude node_modules --strip-cwd-prefix'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_DEFAULT_OPTS='--layout=reverse --preview "bat --style=numbers --color=always --line-range :500 {}"'

# Basic commands
# -----------------------------------------------

# git mis-spellings
abbr --add gt   git
abbr --add gi   git
abbr --add it   git
abbr --add gitt git
abbr --add giit git

# Faster, better grep
abbr --add grep ug

# GMail command line
export PAGER='bat'      # Required for cmdg
export EDITOR='micro'   # Required for cmdg
abbr --add mail cmdg

# Google Calendar command line
abbr --add gcalcli 'uvx gcalcli'
abbr --add agenda 'uvx gcalcli agenda --calendar $EMAIL --nodeclined $(date -Ihours) (date -I --date "+2 days")'

# Color diffs
abbr --add icdiff 'uvx --offline icdiff'

# Jupyter Lab
abbr --add jupyter-lab 'uvx --offline --from jupyterlab jupyter-lab'

# Convert PDF to text
abbr --add pdftotext 'PYTHONUTF8=1 uvx markitdown'

# Clipboard Utilities
# -----------------------------------------------

# Convert unicode characters to ASCII. Useful to strip em-dashes, smart quotes, etc. from ChatGPT
abbr --add ascii 'xclip -selection clipboard -o | uv run --with anyascii python -c "import sys, anyascii; sys.stdout.write(anyascii.anyascii(sys.stdin.read()))" | xclip -selection clipboard'

# Copy to clipboard. Typical usage: command | clip
abbr --add clip 'xclip -selection clipboard'

# Convert clipboard to Markdown rich text. Useful to copy Markdown and paste into GMail.
abbr --add md2rtf 'xclip -sel clip -o | pandoc -f markdown -t html --syntax-highlighting=none | xclip -sel clip -t text/html -i'

# Convert clipboard to Markdown HTML. Useful to copy Markdown and paste into code.
abbr --add md2html 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript -t html --no-highlight --wrap=none | xclip -sel clip -i'

# LLM Utilities
# -----------------------------------------------

# Run Claude Code
abbr --add claude 'npx -y @anthropic-ai/claude-code'
abbr --add claude-yolo 'npx -y @anthropic-ai/claude-code --dangerously-skip-permissions'

# File Utilities
# -----------------------------------------------

# List files, sorted by time, with git status and relative time
abbr --add l 'eza -l -snew --git --time-style relative --no-user --no-permissions --color-scale=size'

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
#     volume=6                   # *4 dB boost on the mic path before mixing (volume=4 => +12 dB)
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
  read -l -P "Use HEADSET to avoid echo. Press ENTER: "
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
    [0:a]highpass=f=100,lowpass=f=12000,afftdn=nf=-30,volume=7[m]; \
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
    -video_size 1920x1080 \
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

abbr --add youtube-dl 'uvx --with mutagen yt-dlp'
abbr --add youtube-opus 'uvx --with mutagen yt-dlp --extract-audio --audio-format opus --embed-thumbnail --postprocessor-args "FFmpegAudioConvertor:-c:a libopus -b:a 12k -ac 1 -application voip -vbr off -ar 8000 -cutoff 4000 -frame_duration 60 -compression_level 10"'
abbr --add youtube-audio 'uvx --with mutagen yt-dlp --extract-audio --audio-format opus --embed-thumbnail'
abbr --add youtube-mp3 'uvx --with mutagen yt-dlp --extract-audio --audio-format mp3 --audio-quality 5'
abbr --add yt-dlp 'uvx --with mutagen yt-dlp'


# List all JSON paths in a file. Usage: cat file.json | jqpaths
abbr --add jqpaths jq -r 'paths(scalars)|map(if type=="number" then "[]" else ".\(. )" end)|join("")|unique[]'
abbr --add shorten 'llm --system "Suggest 5 alternatives that a VERY concise, with fewer words"'
abbr --add transcribe 'llm -m gemini-2.5-flash -s "Transcribe. Drop um, uh, etc. for smooth speech. Make MINIMAL corrections. Break into logical paragraphs. Begin each paragraph with a timestamp. Format as Markdown. Use *emphasis* or **bold** for key points. Prefix audience questions with Question: ... and answers with Answer: ..." -a'
abbr --add unbrace 'npx -y jscodeshift -t $HOME/code/scripts/unbrace.js'
# TODO: Use cwebp -sns for color reduction with -lossless. Experiment for the right setting
# abbr --add webp-lossless 'magick mogrify -format webp +dither -define webp:lossless=true -define webp:method=6 -colors 8'
abbr --add webp-lossy 'cwebp -q 10 -m 6'

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

# Like llm -e but with streaming.
function copycode --description 'Stream + copy last code fence. Usage: llm "Write Tetris in Python" | copycode'
    tee /dev/tty | awk 'BEGIN{f=0} /```/{f=!f; next} f{buf=buf$0"\n"} END{print buf}' | xclip -selection clipboard
end

function pasteit --description "Paste output into buffer. Usage: llm -t fish 'Largest file' | pasteit"
    read -l buf
    commandline -r -- $buf
    commandline -f repaint
end

function livesync --description "Update main from live branch. Create new live branch from main."
    git checkout main
    git merge --squash live
    git diff --cached | llm -t gitcommit | git commit -F -
    git push
    git branch -D live
    git push origin --delete live
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

function with --description "Example: with gh,jq 'Find last 3 repos I committed to'"
    llm --system "Write JUST a fish command using $argv[1]" "$argv[2..]" \
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

function secret --description "Extract secret from .env"
    awk -F= -v k="$argv[1]" '$1==k{print substr($0,index($0,"=")+1);exit}' $HOME/Dropbox/scripts/.env
end

function youtube-subtitles --description "downloads subtitles from YouTube video URL"
    curl -s "$(yt-dlp -q --skip-download --convert-subs srt --write-sub --sub-langs "en" --write-auto-sub --print "requested_subtitles.en.url" $argv[1])"
end

function opus --description "opus file.mp4 converts it to file.opus (voice quality)"
    ffmpeg -hide_banner -stats -v warning -i $argv[1] -c:a libopus -b:a 12k -ac 1 -application voip -vbr on -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $argv[1])
end

# -b:a 48k is OK for many tracks. 64k works for all on earphones. 80-96k for electronic/classical music
# -ac 2 is not required. Mono stays mono. 5.1 downmixes to 2 because Opus is max 2 channels
# -ar 48000 is Opus' native sampling rate
# -frame_duration 60 is more efficient for music than the default 20 or 40 ms
function opusmusic --description "opus file.mp4 converts it to file.opus (music quality)"
    ffmpeg -hide_banner -stats -v warning -i $argv[1] -c:a libopus -b:a 48k -application audio -frame_duration 60 -vbr on -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $argv[1])
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


# Print Codex CLI session logs (from ~/.codex/sessions/yyyy/mm/dd/*.jsonl) as Markdown
function codexlog
    jq -r '
    def h(t):        "\n\n## " + t + "\n\n";
    def summary(t):  "<summary><strong>" + t + "</strong></summary>\n\n";
    def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
    def kv(k; v):    if v then "**" + k + ":** " + v + "\n" else "" end;

    . as $e
    | .payload.type as $t
    | if ($t == "user_message" or $t == "agent_message") then
        h($t) + ($e.payload.message // "")

    elif $t == "agent_reasoning" then
        "\n\n<details>"
        + summary("agent reasoning")
        + ($e.payload.text // $e.payload.message // "")
        + "\n\n</details>"

    elif $t == "function_call" then
        ($e.payload.arguments? | fromjson? // {}) as $A
        | "\n\n<details>"
        + summary("tool: " + ($e.payload.name // ""))
        + (if $A.command? then code("bash"; ($A.command | join(" "))) else "" end)
        + "\n\n</details>"

    elif $t == "function_call_output" then
        ($e.payload.output? | fromjson? // {}) as $O
        | "\n\n<details>"
        + summary("tool output")
        + (if $O.metadata? then
            "**exit:** \($O.metadata.exit_code // "unknown") · **duration:** \($O.metadata.duration_seconds // "unknown")s\n"
        else "" end)
        + code("txt"; ($O.output // ""))
        + "\n\n</details>"

    else empty end
    ' $argv[1]
end

# Print Claude Code session logs (from ~/.claude/projects/$path/*.jsonl) as Markdown

function claudelog
    jq -r '
    def h(t):        "\n\n## " + t + "\n\n";
    def code(l; s):  "```" + l + "\n" + (s // "") + "\n```\n";
    def has_text($s): ($s | test("[^[:space:]]"));

    def details($label; $body):
        "\n\n<details><summary><strong>" + $label + "</strong></summary>\n\n"
        + (if has_text($body) then $body + "\n\n" else "" end)
        + "</details>";

    def tool_use_line($owner; $item):
        ($owner + ": tool: " + ($item.name // "")) as $label
        | (if $item.input? then code("json"; ($item.input | tojson)) else "" end) as $body
        | details($label; $body);

    def tool_result_line($owner; $item):
        ($owner + ": tool result" + (if $item.tool_use_id then ": " + $item.tool_use_id else "" end)) as $label
        | (if ($item.content? // null) == null then ""
           elif ($item.content | type) == "string" then
               if ($item.content | test("[^[:space:]]")) then code("txt"; ($item.content // "")) else "" end
           else code("json"; ($item.content | tojson))
           end) as $body
        | details($label; $body);

    def render($owner; $content):
        if ($content | type) == "string" then
            {text: ($content // ""), extras: [], has_text: has_text($content // "")}
        elif ($content | type) == "array" then
            (reduce $content[] as $item (
                {text:"", extras: []};
                if $item.type == "text" then
                    .text += (if has_text(.text) then "\n\n" else "" end) + ($item.text // "")
                elif $item.type == "tool_use" then
                    .extras += [tool_use_line($owner; $item)]
                elif $item.type == "tool_result" then
                    .extras += [tool_result_line($owner; $item)]
                else .
                end
            )) as $acc
            | $acc + {has_text: has_text($acc.text)}
        else
            {text:"", extras: [], has_text:false}
        end;

    . as $e
    | .type as $owner
    | if ($owner == "user" or $owner == "assistant" or $owner == "system") then
        (render($owner; .message.content)) as $parts
        | (if $parts.has_text then h($owner) + $parts.text else "" end)
        + (if ($parts.extras | length) > 0 then
            (if $parts.has_text then "\n\n" else "" end) + ($parts.extras | join("\n\n"))
          else "" end)
        + (if $owner == "user" and (.toolUseResult? != null) then
            (if $parts.has_text or ($parts.extras | length) > 0 then "\n\n" else "" end)
            + details("user: tool result: meta"; code("json"; (.toolUseResult | tojson)))
          else "" end)
    else empty end
    ' $argv[1]
end


type -q fzf; and fzf --fish | source
type -q zoxide; and zoxide init fish | source
type -q starship; and starship init fish | source

# I store secrets in a .env file. But it's unsafe to source them in every shell. #TODO Use direnv
# source "/c/Dropbox/scripts/.env"
