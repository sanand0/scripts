#!/usr/bin/env -S jq --raw-output --from-file

# Usage
#   cat file.json | tsv.jq
#   cat file.json | jq -r ".items" | tsv.jq

# Extract header from first object
(.[0] | keys_unsorted as $headers | $headers | @tsv),

# Extract data rows
(.[] | . as $row | [.[$row | keys_unsorted[]]] | @tsv)
