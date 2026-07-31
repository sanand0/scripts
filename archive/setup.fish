# Unused fish functions from setup.fish

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
