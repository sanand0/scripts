#!/bin/sh
# Reuse file actions; enumerate directories only on demand.
ROFI_PROVIDER=directories exec "$(dirname "$0")/rofi-files.sh" "$@"
