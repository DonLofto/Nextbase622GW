#!/bin/bash
# Finder entry point for the guided persistent repair; keep the Mac awake.
KIT=$(cd -P "$(dirname "$0")" && pwd) || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    printf 'Python 3.9 or newer is required. Install it, then reopen this launcher.\n'
    result=1
else
    /usr/bin/caffeinate -i python3 "$KIT/persistent-repair/repair.py" "$@"
    result=$?
fi
if [ -t 0 ]; then
    printf '\nPress Return to close this window. '
    IFS= read -r answer
fi
exit "$result"
