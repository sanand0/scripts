#!/bin/bash

FRECENT="$HOME/.cache/sanand-scripts/frecent.txt"

# No arguments => list all files.
if [[ $# -eq 0 ]]; then
    # Show most frequent-recent ($FRECENT) files
    tail -n 1000 "$FRECENT" | sort | uniq -c | sort -rn | awk '{print $2}'
    # Show all other files
    cat $HOME/.cache/sanand-scripts/files*.txt
# Argument => Store in $FRECENT and open it
else
    echo "$*" >> "$FRECENT"
    setsid open "$HOME/$*" >/dev/null 2>&1 &
fi
