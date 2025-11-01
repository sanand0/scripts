#!/bin/bash

FRECENT="$HOME/.cache/sanand-scripts/frecent.txt"

# No arguments => list all files.
if [[ $# -eq 0 ]]; then
    # Show most frequent-recent ($FRECENT) files
    tail -n 1000 "$FRECENT" \
        | sort \
        | uniq -c \
        | sort -rn \
        | awk '{$1=""; sub(/^ /, ""); print}'
    # Show all other files
    cat $HOME/.cache/sanand-scripts/files*.txt

else
    # Prepend file $* to $FRECENT
    { echo "$*"; cat "$FRECENT"; } > "${FRECENT}.tmp"
    mv "${FRECENT}.tmp" "$FRECENT"
    # Open the file $*
    setsid open "$HOME/$*" >/dev/null 2>&1 &
fi
