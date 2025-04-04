#!/bin/bash

FRECENT="$HOME/.config/files.frecent.txt"

if [[ $# -eq 0 ]]; then
    tail -n 1000 "$FRECENT" | sort | uniq -c | sort -rn | awk '{print $2}'
    cat $HOME/.config/files.txt
else
    echo "$*" >> "$FRECENT"
    open "$HOME/$*"
fi
