# Archived fish functions from setup.fish

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
