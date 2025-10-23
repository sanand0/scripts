#!/usr/bin/env -S jq --raw-output --from-file

# Usage
#   cat file.json | tsv.jq
#   cat file.json | jq -r ".items" | tsv.jq

(.[0] | keys_unsorted | @tsv),
(.[] | [.[]] | @tsv)
