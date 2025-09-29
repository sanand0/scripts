# Post-mortem debugger for Python scripts. Starts debugger on unhandled exceptions.
#
# Usage: PYTHONPATH=~/code/scripts/pdbhook uv run script.py
#
# https://chatgpt.com/c/68d8be28-f064-8324-84be-cf1054d5d3be

import sys
import traceback
import pdb


def _pm_excepthook(exc_type, exc, tb):
    if exc_type is SystemExit:
        raise exc
    traceback.print_exception(exc_type, exc, tb)
    pdb.post_mortem(tb)


sys.excepthook = _pm_excepthook
