#!/usr/bin/env -S jq --raw-output --from-file

# Usage
#   cat file.json | tsv.jq
#   cat file.json | jq -r ".items" | tsv.jq

# Build a header from the union of keys (sorted), then print header and rows.
($keys := (reduce .[] as $o ({}; . + $o) | keys))
| ($keys | @tsv),
  (.[] | [ $keys[] as $k | .[$k] // "" ] | @tsv)
