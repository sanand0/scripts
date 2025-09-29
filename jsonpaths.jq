#!/usr/bin/env -S jq --null-input --raw-output --from-file

# List unique JSON paths across all inputs (JSON or NDJSON).
# Array indices are canonicalized to [*] so [0], [1], ... collapse to a single pattern.
# https://chatgpt.com/c/68d8ceb8-d2dc-8333-b3c3-15b5ac4f1460
#
# Usage:
#   jsonpaths.jq FILE                # leaf paths (default)
#   jsonpaths.jq --arg mode all FILE # include container nodes too

def _ident_re: "^[A-Za-z_][A-Za-z0-9_]*$";

# Convert a jq path array to a jq-style path string with [*] for any array index.
def _pstr:
  map(
    if type == "number" then "[*]"                                # <-- de-dupe array indices
    elif type == "string" then
      if test(_ident_re) then "." + .
      else "[" + tojson + "]"
      end
    else "[" + tojson + "]"
    end
  )
  | join("");

($ARGS.named.mode // "leaves") as $mode
| reduce (
    inputs
    | if $mode == "all"
      then (paths(scalars), paths(objects), paths(arrays))         # include containers if requested
      else paths(scalars)
      end
    | _pstr
  ) as $p ({}; .[$p] = true)
| keys
| sort[]
