#!/bin/bash
# Files and directories share context actions; the launcher selects one provider.
set -euo pipefail
shopt -s nullglob

CACHE="$HOME/.cache/sanand-scripts"
FRECENT="$CACHE/frecent.txt"

row() {
    printf '%s\0info\x1f%s\n' "$1" "$2"
}

resolve_path() {
    case "$1" in
        /*) printf '%s' "$1" ;;
        "~/"*) printf '%s/%s' "$HOME" "${1#\~/}" ;;
        *) printf '%s/%s' "$HOME" "$1" ;;
    esac
}

remember_file() {
    mkdir -p "$CACHE"
    { printf '%s\n' "$1"; [[ ! -f "$FRECENT" ]] || cat "$FRECENT"; } > "$FRECENT.tmp"
    mv "$FRECENT.tmp" "$FRECENT"
}

directories() {
    local score dir label
    declare -A seen=()
    # zoxide orders all visited directories by frecency; include unvisited repos.
    while read -r score dir; do
        [[ -d "$dir" && ! -v seen["$dir"] ]] || continue
        label="$dir"
        [[ "$dir" == "$HOME/"* ]] && label="${dir#"$HOME"/}"
        row "Directory: $label" "directory:$dir"
        seen["$dir"]=1
    done < <(zoxide query -ls 2>/dev/null)
    for dir in "$HOME"/code/*; do
        [[ -d "$dir" && -e "$dir/.git" && ! -v seen["$dir"] ]] || continue
        row "Directory: code/${dir##*/}" "directory:$dir"
        seen["$dir"]=1
    done
}

all_files() {
    local file
    if [[ -f "$FRECENT" ]]; then
        head -n 5000 "$FRECENT" | sort | uniq -c | sort -rn |
            sed -E 's/^ *[0-9]+ //'
    fi
    for file in "$CACHE"/files*.txt; do cat "$file"; done
}

detached() {
    setsid "$@" >/dev/null 2>&1 &
}

clipboard() {
    if command -v xclip >/dev/null 2>&1; then
        xclip -selection clipboard -in
    else
        wl-copy
    fi
}

code_window() {
    local win="${ROFI_SOURCE_WINDOW:-}"
    if [[ "$win" =~ ^[0-9]+$ ]] &&
        xprop -id "$win" WM_CLASS 2>/dev/null | grep -Eqi '"(code|Code|code-oss)"'; then
        printf '%s' "$win"
        return
    fi
    local -a wins=()
    mapfile -t wins < <(xdotool search --onlyvisible --class 'code' 2>/dev/null | sort -u)
    if (("${#wins[@]}" == 1)); then
        printf '%s' "${wins[0]}"
        return
    fi
    notify-send "Rofi directory action" "Open VS Code before using terminal actions (or close extra VS Code windows)." 2>/dev/null || true
    return 1
}

terminal_in() {
    # Use VS Code's direct terminal-focus binding (not the Command Palette).
    # Type real shell commands so fish records them in its history.
    local command="cd -- $(printf '%q' "$1")" win
    [[ -z "${2:-}" ]] || command+=" && $2"
    win="$(code_window)" || return 0
    xdotool windowactivate --sync "$win" || return 0
    xdotool key --clearmodifiers ctrl+alt+shift+F12
    [[ "$(xdotool getactivewindow)" == "$win" ]] || return 0
    xdotool type --clearmodifiers --delay 0 -- "$command"
    xdotool key --clearmodifiers Return
}

github_url() {
    local remote
    remote="$(git -C "$1" remote get-url origin 2>/dev/null)" || return 1
    case "$remote" in
        git@github.com:*) printf 'https://github.com/%s' "${remote#git@github.com:}" ;;
        https://github.com/*) printf '%s' "$remote" ;;
        *) return 1 ;;
    esac | sed 's/\.git$//'
}

do_action() {
    local kind="$1" path="$2" action="$3" dir root uri link
    dir="$path"
    [[ "$kind" == directory ]] || dir="$(dirname "$path")"
    case "$action" in
        open) open_file "$path" ;;
        open-directory) detached xdg-open "$path" ;;
        code) detached code "$path" ;;
        folder-code) detached code "$dir" ;;
        reveal) detached nautilus --select -- "$path" ;;
        terminal) terminal_in "$dir" ;;
        status) terminal_in "$dir" "git status" ;;
        diff)
            if [[ "$kind" == directory ]]; then
                terminal_in "$dir" "git diff"
            else
                terminal_in "$dir" "git diff -- $(printf '%q' "${path##*/}")"
            fi
            ;;
        just) terminal_in "$dir" "just --list" ;;
        codex) terminal_in "$dir" "codex resume" ;;
        claude) terminal_in "$dir" "claude --resume" ;;
        github)
            link="$(github_url "$dir")" && detached xdg-open "$link"
            ;;
        copy-path) printf '%s' "$path" | clipboard ;;
        copy-relative)
            root="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null)" || root=""
            if [[ "$path" == "$root/"* ]]; then
                printf '%s' "${path#"$root"/}" | clipboard
            else
                printf '%s' "$path" | clipboard
            fi
            ;;
        copy-text)
            if [[ -f "$path" ]]; then
                case "$(file -b --mime-type -- "$path")" in
                    text/*|application/json|application/xml|application/javascript) cat "$path" | clipboard ;;
                esac
            fi
            ;;
        copy-file)
            uri="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).as_uri())' "$path")"
            printf 'copy\n%s\n' "$uri" | xclip -selection clipboard -t x-special/gnome-copied-files -in
            ;;
        copy-link)
            uri="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).as_uri())' "$path")"
            printf '[%s](%s)' "${path##*/}" "$uri" | clipboard
            ;;
    esac
}

browse_directory() {
    local dir="$1" chosen status
    local -a opts=(-dmenu -i -no-custom -p "Files: ${dir##*/}" -kb-custom-1 "Control+Return,Alt+Return")
    if command -v fd >/dev/null 2>&1; then
        chosen="$(cd "$dir" && fd -t f --hidden --exclude .git --exclude node_modules . | rofi "${opts[@]}")" && status=0 || status=$?
    else
        chosen="$(cd "$dir" && find . -type d \( -name .git -o -name node_modules \) -prune -o -type f -print | rofi "${opts[@]}")" && status=0 || status=$?
    fi
    [[ -n "$chosen" ]] || return 0
    local path="$dir/$chosen"
    if ((status == 0)); then
        open_file "$path"
    elif ((status >= 10)); then
        action_menu file "$path"
    fi
}

action_menu() {
    local kind="$1" path="$2" index
    local -a labels=() actions=()
    if [[ "$kind" == directory ]]; then
        labels=("Open in Files" "Open terminal in VS Code" "Open directory in VS Code" "Browse directory files" "Copy path")
        actions=(open-directory terminal code browse copy-path)
        if git -C "$path" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            labels+=("Git status (VS Code terminal)" "Git diff (VS Code terminal)" "List just tasks (VS Code terminal)" "Resume Codex (VS Code terminal)" "Resume Claude (VS Code terminal)" "Open GitHub repository")
            actions+=(status diff just codex claude github)
        fi
        labels+=("← Back to directories")
        actions+=(back)
    else
        labels=("Open file" "Open file in VS Code" "Reveal in Files" "Open terminal in VS Code" "Open containing directory in VS Code" "Copy absolute path" "Copy Git-relative path" "Copy file contents" "Copy file for pasting in Files" "Copy Markdown link" "Show Git diff in VS Code terminal" "← Back to search")
        actions=(open code reveal terminal folder-code copy-path copy-relative copy-text copy-file copy-link diff back)
    fi
    index="$(printf '%s\n' "${labels[@]}" | rofi -dmenu -no-custom -i -format i -p "${kind^}: ${path##*/}")" || return 0
    [[ "$index" =~ ^[0-9]+$ ]] && ((index < "${#actions[@]}")) || return 0
    case "${actions[index]}" in
        browse) browse_directory "$path" ;;
        back) detached "$(dirname "$0")/../rofi-picker" "$([[ "$kind" == directory ]] && echo d || echo f)" ;;
        *) do_action "$kind" "$path" "${actions[index]}" ;;
    esac
}

open_file() {
    remember_file "${1#"$HOME"/}"
    if [[ "$1" == "$HOME"/Music/*.mp3 ]]; then
        detached "$HOME/code/scripts/play-music" "$1"
    else
        detached xdg-open "$1"
    fi
}

# Close the picker before opening its separate action menu.
close_picker() {
    local pid
    [[ -n "${ROFI_PICKER_PIDFILE:-}" && -r "$ROFI_PICKER_PIDFILE" ]] || return 0
    read -r pid < "$ROFI_PICKER_PIDFILE"
    [[ "$pid" =~ ^[0-9]+$ ]] && kill -TERM "$pid" 2>/dev/null || true
}

if [[ "${1:-}" == --terminal ]]; then
    terminal_in "$2" "$3"
    exit 0
fi

if [[ "${1:-}" == --menu ]]; then
    # Rofi's default lazy keyboard grab waits for the closing picker to release it.
    action_menu "$2" "$3"
    exit 0
fi

retv="${ROFI_RETV:-0}"
selection="${ROFI_INFO:-$*}"
if [[ "$retv" == 0 ]]; then
    printf '\0use-hot-keys\x1ftrue\n\0no-custom\x1ftrue\n'
    if [[ "${ROFI_PROVIDER:-files}" == directories ]]; then
        directories
    else
        all_files
    fi
elif [[ -n "$selection" ]]; then
    if [[ "$selection" == directory:* ]]; then
        path="${selection#directory:}"
        kind=directory
    else
        path="$(resolve_path "$selection")"
        kind=file
        [[ -d "$path" ]] && kind=directory
    fi
    if ((retv >= 10)); then
        detached "$0" --menu "$kind" "$path"
        close_picker
    elif [[ "$kind" == directory ]]; then
        detached xdg-open "$path"
    else
        open_file "$path"
    fi
fi
