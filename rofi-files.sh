#!/bin/bash
# Ctrl+Alt+F script mode: one picker for files and projects.
set -euo pipefail
shopt -s nullglob
CACHE="$HOME/.cache/sanand-scripts"
FRECENT="$CACHE/frecent.txt"

header() {
    printf '\0use-hot-keys\x1ftrue\n\0no-custom\x1ftrue\n\0prompt\x1f%s\n\0data\x1f%s\n' "$1" "$2"
}

row() {
    printf '%s\0info\x1f%s\n' "$1" "$2"
}

resolve_path() {
    case "$1" in
        /*) printf '%s' "$1" ;;
        "~/"*) printf '%s/%s' "$HOME" "${1#~/}" ;;
        *) printf '%s/%s' "$HOME" "$1" ;;
    esac
}

remember_file() {
    mkdir -p "$CACHE"
    { printf '%s\n' "$1"; [[ ! -f "$FRECENT" ]] || cat "$FRECENT"; } > "$FRECENT.tmp"
    mv "$FRECENT.tmp" "$FRECENT"
}

projects() {
    local dir score
    declare -A seen=()
    # zoxide's scored list puts the most-used repositories first.
    if command -v zoxide >/dev/null 2>&1; then
        while read -r score dir; do
            [[ "$dir" == "$HOME"/code/* && -e "$dir/.git" ]] || continue
            [[ ! -v seen["$dir"] ]] || continue
            row "Project: ${dir#"$HOME"/code/}" "project:$dir"
            seen["$dir"]=1
        done < <(zoxide query -ls 2>/dev/null)
    fi
    for dir in "$HOME"/code/*; do
        [[ -e "$dir/.git" ]] || continue
        [[ ! -v seen["$dir"] ]] || continue
        row "Project: ${dir#"$HOME"/code/}" "project:$dir"
        seen["$dir"]=1
    done
}

all_files() {
    local file
    if [[ -f "$FRECENT" ]]; then
        tail -n 1000 "$FRECENT" | sort | uniq -c | sort -rn |
            awk '{$1=""; sub(/^ /, ""); print}'
    fi
    for file in "$CACHE"/files*.txt; do cat "$file"; done
}

show_global() {
    header "Files / projects" "global"
    projects
    all_files
}

show_browse() {
    local dir="$1" file
    header "Files in ${dir#"$HOME"/}" "browse:$dir"
    row "← Project actions" "back"
    if command -v fd >/dev/null 2>&1; then
        while IFS= read -r file; do
            row "${file#"$HOME"/}" "file:$file"
        done < <(fd -t f -a --hidden --exclude .git --exclude node_modules . "$dir" 2>/dev/null)
    else
        while IFS= read -r file; do
            row "${file#"$HOME"/}" "file:$file"
        done < <(find "$dir" -type d \( -name .git -o -name node_modules \) -prune -o -type f -print 2>/dev/null)
    fi
}

show_actions() {
    local kind="$1" path="$2"
    header "${kind^}: ${path##*/}" "actions:$kind:$path"
    row "← Back to search" "back"
    if [[ "$kind" == project ]]; then
        row "Open terminal here" "terminal"
        row "Open project in VS Code" "code"
        row "Browse project files" "browse"
        row "Git status" "status"
        row "Git diff" "diff"
        row "List just tasks" "just"
        row "Resume Codex session" "codex"
        row "Resume Claude session" "claude"
        row "Open GitHub repository" "github"
    else
        row "Open file" "open"
        row "Open file in VS Code" "code"
        row "Reveal in Files" "reveal"
        row "Open terminal in containing directory" "terminal"
        row "Open containing directory in VS Code" "folder-code"
        row "Copy absolute path" "copy-path"
        row "Copy Git-relative path" "copy-relative"
        row "Copy file contents" "copy-text"
        row "Copy file for pasting in Files" "copy-file"
        row "Copy Markdown link" "copy-link"
        row "Show Git diff for file" "diff"
    fi
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

terminal_in() {
    local dir="$1"
    shift
    if (($#)); then
        detached gnome-terminal --working-directory="$dir" -- bash -lc "$1; exec fish"
    else
        detached gnome-terminal --working-directory="$dir"
    fi
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
    [[ "$kind" == project ]] || dir="$(dirname "$path")"
    case "$action" in
        back) show_global ;;
        browse) show_browse "$path" ;;
        open) detached xdg-open "$path" ;;
        code) detached code "$path" ;;
        folder-code) detached code "$dir" ;;
        reveal) detached nautilus --select -- "$path" ;;
        terminal) terminal_in "$dir" ;;
        status) terminal_in "$dir" "git status" ;;
        diff)
            if [[ "$kind" == project ]]; then
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

state="${ROFI_DATA:-global}"
retv="${ROFI_RETV:-0}"
selection="${ROFI_INFO:-$*}"

if [[ "$retv" == 0 ]]; then
    show_global
elif [[ "$state" == actions:* ]]; then
    kind="${state#actions:}"
    path="${kind#*:}"
    kind="${kind%%:*}"
    if [[ "$selection" == back ]]; then
        show_global
    else
        do_action "$kind" "$path" "$selection"
    fi
elif [[ "$state" == browse:* && "$selection" == back ]]; then
    show_actions project "${state#browse:}"
elif [[ "$selection" == project:* ]]; then
    show_actions project "${selection#project:}"
elif [[ "$selection" == file:* ]]; then
    path="${selection#file:}"
    if ((retv >= 10)); then
        show_actions file "$path"
    else
        remember_file "${path#"$HOME"/}"
        if [[ "$path" == "$HOME"/Music/*.mp3 ]]; then
            detached "$HOME/code/scripts/play-music" "$path"
        else
            detached xdg-open "$path"
        fi
    fi
elif [[ -n "$selection" ]]; then
    path="$(resolve_path "$selection")"
    if [[ -d "$path" ]]; then
        show_actions project "$path"
    elif ((retv >= 10)); then
        show_actions file "$path"
    else
        remember_file "$selection"
        if [[ "$path" == "$HOME"/Music/*.mp3 ]]; then
            detached "$HOME/code/scripts/play-music" "$path"
        else
            detached xdg-open "$path"
        fi
    fi
fi

