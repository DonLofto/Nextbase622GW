#!/bin/bash
# Finder double-click entry point; the preparation script owns all card changes.
KIT=$(cd -P "$(dirname "$0")" && pwd) || exit 1
/bin/bash "$KIT/prepare-macos.sh" prepare "$@"
result=$?
if [ -t 0 ]; then
    printf '\nPress Return to close this window. '
    IFS= read -r answer
fi
exit "$result"
