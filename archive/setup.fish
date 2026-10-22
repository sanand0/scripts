# Archived fish functions from setup.fish

# Archived: 22 Oct 2026. I don't use shorten - I use Google.
abbr --add shorten 'llm --system "Suggest 5 alternatives that a VERY concise, with fewer words"'
# Archived: 22 Oct 2026. Replaced transcribe with ~/code/scripts/transcribe.
abbr --add transcribe 'llm -m gemini-3.1-pro-preview -s "Transcribe. Drop um, uh, etc. for smooth speech. Make MINIMAL corrections. Break into logical paragraphs. Begin each paragraph with a timestamp. Format as Markdown. Use *emphasis* or **bold** for key points. Prefix audience questions with Question: ... and answers with Answer: ..." -a'
# Archived: 22 Oct 2026. I use the `-claude` keyboard shortcut.
abbr --add claude-yolo 'npx -y @anthropic-ai/claude-code --dangerously-skip-permissions'

# Archived: 22 Oct 2026. I use rofi-clip.sh now. Convert unicode characters to ASCII. Useful to strip em-dashes, smart quotes, etc. from ChatGPT
abbr --add ascii 'xclip -selection clipboard -o | uv run --with anyascii python -c "import sys, anyascii; sys.stdout.write(anyascii.anyascii(sys.stdin.read()))" | xclip -selection clipboard'
# Archived: 22 Oct 2026. I use rofi-clip.sh now. Convert clipboard to Markdown rich text. Useful to copy Markdown and paste into GMail.
abbr --add md2rtf 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript+hard_line_breaks -t html --syntax-highlighting=none --wrap=none | xclip -sel clip -t text/html -i'
# Archived: 22 Oct 2026. I use rofi-clip.sh now. Convert clipboard to Markdown HTML. Useful to copy Markdown and paste into code.
abbr --add md2html 'xclip -sel clip -o | pandoc -f gfm-gfm_auto_identifiers+bracketed_spans+fenced_divs+subscript+superscript+hard_line_breaks -t html --syntax-highlighting=none --wrap=none | xclip -sel clip -i'

# Archived: 24 Aug 2026. I no longer use these tools and the .venv directories are large.
mkdir -p ~/apps/openwebui; cd ~/apps/openwebui; uv venv --python 3.11; source .venv/bin/activate.fish; uv pip install open-webui
mkdir -p ~/apps/whisper-ctranslate2; cd ~/apps/whisper-ctranslate2; uv venv --python 3.11; source .venv/bin/activate.fish; UV_TORCH_BACKEND=auto uv pip install whisper-ctranslate2 nvidia-cublas-cu12 nvidia-cudnn-cu12==9.1.1.17 nvidia-cuda-runtime-cu12==12.4.127 librosa soundfile torch torchaudio
mkdir -p ~/apps/whisper-ctranslate2; cd ~/apps/whisper-ctranslate2; uv venv --python 3.11; source .venv/bin/activate.fish;
  uv pip install whisper-ctranslate2 nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cuda-runtime-cu12  # for faster-whisper
  UV_TORCH_BACKEND=auto uv pip install torch torchaudio   # for whisper_streaming

cd ~/.local/bin; curl -L https://github.com/OpenWhispr/openwhispr/releases/latest/download/OpenWhispr-1.6.10-linux-x86_64.AppImage -o openwhispr && chmod +x openwhispr   # OpenWhispr - GUI for whisper-ctranslate2 live transcription. Ctrl+Shift+D to dictate.
sudo apt install -y libportaudio2 portaudio19-dev   # for python -m sounddevice used by whisper-ctranslate2 live transcription

set -gx PATH $PATH "$HOME/apps/whisper-ctranslate2/.venv/bin"

# whisper --output_format txt $inputfile
function whisper --description "transcribe audio file using Whisper Ctranslate2"
    source $HOME/apps/whisper-ctranslate2/.venv/bin/activate.fish
    export LD_LIBRARY_PATH="/home/sanand/apps/whisper-ctranslate2/.venv/lib64/python3.11/site-packages/nvidia/cublas/lib/:/home/sanand/apps/whisper-ctranslate2/.venv/lib64/python3.11/site-packages/nvidia/cudnn/lib/"
    whisper-ctranslate2 --device cuda --language en $argv[1..]
    deactivate
end

# Archived: 15 Aug 2026. Migrated to ~/code/scripts/pages since pressing Ctrl+C leaves cloudflared running in the background.
# https://chatgpt.com/c/6a807fda-7f00-83ee-8a6e-77bdfaa6bcf5
function pages --description "pages XXX serves pwd at https://pages.s-anand.net/XXX/"
    set base $argv[1]
    test -n "$base"; or set base "/"

    if not string match -q '/*' "$base"
        set base "/$base"
    end
    if not string match -q '*/' "$base"
        set base "$base/"
    end

    set port 9000
    set host pages.s-anand.net
    set started_cloudflared 0

    if not pgrep -x cloudflared >/dev/null
        set started_cloudflared 1
        cloudflared tunnel run --token (secret CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN) &
        set cloudflared_pid $last_pid
    end

    env __VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=$host \
        npx --yes vite . \
        --host 127.0.0.1 \
        --port $port \
        --strictPort \
        --base "$base"

    set vite_status $status

    if test $started_cloudflared -eq 1
        kill $cloudflared_pid 2>/dev/null
    end

    return $vite_status
end

# Archived: 31 Jul 2026. I'm not using llm much on the CLI. Agents have taken over.
# Like llm -e but with streaming.
function copycode --description 'Stream + copy last code fence. Usage: llm "Write Tetris in Python" | copycode'
    tee /dev/tty | awk 'BEGIN{f=0} /```/{f=!f; next} f{buf=buf$0"\n"} END{print buf}' | xclip -selection clipboard
end

# Archived: 31 Jul 2026. I'm not using llm much on the CLI. Agents have taken over.
function pasteit --description "Paste output into buffer. Usage: llm -t fish 'Largest file' | pasteit"
    read -l buf
    commandline -r -- $buf
    commandline -f repaint
end

# Archived: 31 Jul 2026. I'm not using llm much on the CLI. Agents have taken over.
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

# Archived: 31 Jul 2026. I use MP3 for music (VLC, mp3 tags, etc.) and Opus only for voice. So this is unused.
# -b:a 48k is OK for many tracks. 64k works for all on earphones. 80-96k for electronic/classical music
# -ac 2 is not required. Mono stays mono. 5.1 downmixes to 2 because Opus is max 2 channels
# -ar 48000 is Opus' native sampling rate
# -frame_duration 60 is more efficient for music than the default 20 or 40 ms
function opusmusic --description "opus *.mp4 converts it to *.opus (music quality)"
    for file in $argv
        ffmpeg -hide_banner -stats -v warning -i $file -c:a libopus -b:a 48k -application audio -frame_duration 60 -vbr on -cpu-used 8 -compression_level 10 (string replace -r '\.[^.]+$' '.opus' $file)
    end
end
