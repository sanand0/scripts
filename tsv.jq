#!/usr/bin/env -S jq --raw-output --from-file

# Usage
#   cat file.json | tsv.jq
#   cat file.json | jq -r ".items" | tsv.jq

# Extract header from first object and use that order for every data row.
if length == 0 then empty else
  (.[0] | keys_unsorted) as $headers |
  ($headers | @tsv), (.[] | [.[$headers[]]] | @tsv)
end
