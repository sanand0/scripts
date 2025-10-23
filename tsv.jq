#!/usr/bin/env -S jq --raw-output --from-file

def to_tsv:
  if type == "array" and length > 0 then
    (.[0] | keys_unsorted | @tsv),
    (.[] | [.[]] | @tsv)
  else
    empty
  end;

(eval($ARGS.positional[0])) | to_tsv
