#!/bin/bash

FRECENT="$HOME/.config/sanand-scripts/files.frecent.txt"

if [[ $# -eq 0 ]]; then
    tail -n 1000 "$FRECENT" | sort | uniq -c | sort -rn | awk '{print $2}'
    cat $HOME/.config/sanand-scripts/files.txt $HOME/.config/hetzner.txt
else
    echo "$*" >> "$FRECENT"
    setsid open "$HOME/$*" >/dev/null 2>&1 &
fi
