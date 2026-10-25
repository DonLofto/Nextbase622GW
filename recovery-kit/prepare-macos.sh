#!/bin/bash
# Native macOS / Bash 3.2 installer. Only the named recovery files are managed.
set -u
umask 077
export LC_ALL=C
shopt -s nullglob dotglob

OWNER='Nextbase622GW Bluetooth Recovery Kit 0.2.0'
MARKER='nb-bt-recovery-kit.txt'
GUARD='nb-bt-recovery.claimed'
FILES=('autoexec.ash' 'nb-bt-recover.sh' 'usb.console')
HASHES=('' '' '')
KIT=$(cd -P "$(dirname "$0")" && pwd) || exit 1
VOLUME=''
STAGE=''
PENDING=''
COMMITTED=()
PREPARED=0

fail() {
    printf 'Recovery kit: %s\n' "$*" >&2
    exit 1
}

exists() { [ -e "$1" ] || [ -L "$1" ]; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }

digest() {
    local result
    result=$(/usr/bin/shasum -a 256 "$1") || return 1
    printf '%s' "${result%% *}"
}

owner_matches() {
    regular "$1" && cmp -s "$1" <(printf '%s\n' "$OWNER")
}

expected_hash() {
    case "$1" in
        autoexec.ash) printf '%s' "${HASHES[0]}" ;;
        nb-bt-recover.sh) printf '%s' "${HASHES[1]}" ;;
        usb.console) printf '%s' "${HASHES[2]}" ;;
        *) return 1 ;;
    esac
}

matches() {
    local actual expected
    regular "$1" || return 1
    expected=$(expected_hash "$2") || return 1
    actual=$(digest "$1") || return 1
    [ "$actual" = "$expected" ]
}

verify_kit() {
    local hash name extra index count=0 seen=' '
    [ -d "$KIT/payload" ] && [ ! -L "$KIT/payload" ] || fail 'Missing or linked payload directory.'
    regular "$KIT/SHA256SUMS" || fail 'Missing or linked SHA256SUMS.'
    while read -r hash name extra || [ -n "${hash}${name}${extra}" ]; do
        [ -n "${hash}${name}${extra}" ] || continue
        [[ "$hash" =~ ^[[:xdigit:]]{64}$ ]] || fail 'Malformed payload manifest.'
        [ -z "$extra" ] || fail 'Malformed payload manifest.'
        case "$name" in
            autoexec.ash) index=0 ;;
            nb-bt-recover.sh) index=1 ;;
            usb.console) index=2 ;;
            *) fail 'Unexpected filename in payload manifest.' ;;
        esac
        case "$seen" in *" $name "*) fail 'Duplicate payload manifest entry.' ;; esac
        seen="$seen$name "
        HASHES[$index]=$(printf '%s' "$hash" | tr 'A-F' 'a-f')
        count=$((count + 1))
    done < "$KIT/SHA256SUMS"
    [ "$count" -eq 3 ] || fail 'Manifest must list exactly three payload files.'
    for name in "${FILES[@]}"; do
        matches "$KIT/payload/$name" "$name" || fail "Payload verification failed: $name. Download a fresh kit."
    done
}

compatible() {
    regular "$1/Nextbase.info" || return 1
    awk '
        tolower($0) ~ /^[[:space:]]*model[[:space:]]*:/ {
            model_count++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value);
            sub(/[[:space:]]*$/, "", value); model=value
        }
        tolower($0) ~ /^[[:space:]]*firmware[[:space:]]*:/ {
            firmware_count++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value);
            sub(/[[:space:]]*$/, "", value); firmware=value
        }
        END { exit !(model_count == 1 && firmware_count == 1 && model == "622GW" && firmware == "R13.3") }
    ' "$1/Nextbase.info"
}

select_volume() {
    local candidate found='' count=0 search_root
    if [ -n "$1" ]; then
        VOLUME=$1
    else
        # Custom mount roots are also useful for offline preparation and tests.
        search_root=${NB_RECOVERY_VOLUMES_ROOT:-/Volumes}
        [ -d "$search_root" ] && [ ! -L "$search_root" ] || fail 'No mounted-card search directory. Supply the card path.'
        for candidate in "$search_root"/*; do
            [ -d "$candidate" ] && [ ! -L "$candidate" ] || continue
            if compatible "$candidate"; then found=$candidate; count=$((count + 1)); fi
        done
        [ "$count" -eq 1 ] || fail 'Expected exactly one compatible card. Supply its path explicitly.'
        VOLUME=$found
    fi
    while [ "$VOLUME" != / ] && [[ "$VOLUME" = */ ]]; do VOLUME=${VOLUME%/}; done
    [ -d "$VOLUME" ] && [ ! -L "$VOLUME" ] || fail 'Card path must be an existing directory, not a symbolic link.'
    VOLUME=$(cd -P "$VOLUME" && pwd) || fail 'Cannot resolve the card directory.'
    compatible "$VOLUME" || fail 'Nextbase.info must contain exactly one Model: 622GW and Firmware: R13.3 field.'
}

check_collisions() {
    local path name lower
    for path in "$VOLUME"/*; do
        name=${path##*/}
        lower=$(printf '%s' "$name" | tr 'A-Z' 'a-z')
        case "$lower" in
            fw*.bin|ld*.bin)
                fail 'Root firmware files are present. Remove them from this preparation workflow first.' ;;
            bt-diagnostics.sh|bt-late-diagnostics.sh|bt-start-test.sh|bt-storage-diagnostics.sh|bt-*.claimed)
                fail 'Legacy diagnostics are present; preserve and remove their startup files before using this kit.' ;;
            autoexec*.ash|usb*.console|nb-bt-recover.sh|nb-bt-recovery-kit.txt|nb-bt-recovery.claimed)
                if [ "$ACTION" = prepare ]; then
                    fail 'Existing startup, console, or recovery files found. Nothing was overwritten; use status or remove for an owned kit.'
                fi
                case "$name" in
                    autoexec.ash|usb.console|nb-bt-recover.sh|nb-bt-recovery-kit.txt|nb-bt-recovery.claimed) ;;
                    *) fail 'An unknown startup or console hook is present. Nothing was changed.' ;;
                esac ;;
        esac
    done
}

verify_guard() {
    local path
    exists "$VOLUME/$GUARD" || return 0
    [ -d "$VOLUME/$GUARD" ] && [ ! -L "$VOLUME/$GUARD" ] || fail 'Runtime guard is not an owned directory.'
    owner_matches "$VOLUME/$GUARD/owner.txt" || fail 'Runtime guard ownership differs. Nothing was changed.'
    for path in "$VOLUME/$GUARD"/*; do
        [ "${path##*/}" = owner.txt ] || fail 'Runtime guard contains unknown files. Nothing was changed.'
    done
}

verify_owned() {
    local name
    owner_matches "$VOLUME/$MARKER" || fail 'Recovery ownership marker is missing or changed. Nothing was changed.'
    for name in "${FILES[@]}"; do
        if [ "$name" = usb.console ] && ! exists "$VOLUME/$name"; then continue; fi
        matches "$VOLUME/$name" "$name" || fail "Owned payload is missing, linked or modified: $name. Nothing was changed."
    done
    verify_guard
}

remove_rollback_file() {
    local name=$1
    if [ "$name" = "$MARKER" ]; then
        owner_matches "$VOLUME/$name" || return 0
    else
        matches "$VOLUME/$name" "$name" || return 0
    fi
    rm -f "$VOLUME/$name" || printf 'Could not roll back %s; remove the startup hook before rebooting.\n' "$name" >&2
}

cleanup() {
    local status=$? index
    trap - EXIT HUP INT TERM
    if [ "$PREPARED" -eq 0 ]; then
        # A signal can arrive after rename succeeds but before COMMITTED updates.
        if [ -n "$PENDING" ] && [ -n "$STAGE" ] && ! exists "$STAGE/$PENDING"; then
            remove_rollback_file "$PENDING"
        fi
        index=${#COMMITTED[@]}
        while [ "$index" -gt 0 ]; do
            index=$((index - 1))
            remove_rollback_file "${COMMITTED[$index]}"
        done
    fi
    if [ -n "$STAGE" ]; then rm -rf "$STAGE"; fi
    exit "$status"
}

commit_file() {
    local name=$1
    exists "$VOLUME/$name" && fail 'A destination appeared during preparation. Installation was stopped.'
    PENDING=$name
    mv -n "$STAGE/$name" "$VOLUME/$name" || fail 'Could not install a payload; rolling back.'
    ! exists "$STAGE/$name" || fail 'A destination collision stopped preparation; rolling back.'
    COMMITTED[${#COMMITTED[@]}]=$name
    PENDING=''
}

prepare_card() {
    local name
    [ -w "$VOLUME" ] || fail 'Card is not writable. Use a writable card reader; no sudo is needed.'
    STAGE=$(mktemp -d "$VOLUME/.nb-bt-recovery.stage.XXXXXXXX") || fail 'Cannot create a staging directory on the card.'
    trap cleanup EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM
    for name in "${FILES[@]}"; do
        cp "$KIT/payload/$name" "$STAGE/$name" || fail 'Staged copy failed; no boot hook was installed.'
        matches "$STAGE/$name" "$name" || fail 'Staged payload verification failed; no boot hook was installed.'
    done
    printf '%s\n' "$OWNER" > "$STAGE/$MARKER" || fail 'Cannot stage the ownership marker.'
    # Arm the startup hook last, only after all staged payloads pass verification.
    commit_file "$MARKER"
    commit_file nb-bt-recover.sh
    commit_file usb.console
    commit_file autoexec.ash
    verify_owned
    PREPARED=1
    printf 'Prepared the temporary Bluetooth recovery kit. Existing videos and results were preserved.\n'
    printf 'Safely eject the card in Finder and insert it into the powered-off camera.\n'
    printf 'Reconnect the camera to this computer with a USB data cable in the camera body, then power it on.\n'
    printf 'Wait about one minute, then use the camera pairing menu and the Nextbase phone app.\n'
    printf 'This prepares an attempt; it does not confirm successful pairing or a persistent repair.\n'
}

remove_card() {
    verify_owned
    [ -w "$VOLUME" ] || fail 'Card is not writable.'
    # Disarm startup first. Never recursively remove result directories.
    rm "$VOLUME/autoexec.ash" || fail 'Could not remove the boot hook; removal stopped.'
    if exists "$VOLUME/usb.console"; then rm "$VOLUME/usb.console" || fail 'Could not remove the owned console token.'; fi
    rm "$VOLUME/nb-bt-recover.sh" || fail 'Could not remove the owned recovery script.'
    if exists "$VOLUME/$GUARD"; then
        rm "$VOLUME/$GUARD/owner.txt" && rmdir "$VOLUME/$GUARD" || fail 'Could not remove the owned runtime guard.'
    fi
    rm "$VOLUME/$MARKER" || fail 'Could not remove the ownership marker.'
    printf 'Recovery startup files removed. Videos, user files and recovery results were preserved.\n'
    printf 'Safely eject the card in Finder before disconnecting it.\n'
}

ACTION=${1:-prepare}
[ "$#" -le 2 ] || fail 'Usage: bash prepare-macos.sh prepare|status|remove [volume]'
case "$ACTION" in prepare|status|remove) ;; *) fail 'Usage: bash prepare-macos.sh prepare|status|remove [volume]' ;; esac
verify_kit
select_volume "${2:-}"
check_collisions
case "$ACTION" in
    prepare) prepare_card ;;
    remove) remove_card ;;
    status)
        if exists "$VOLUME/$MARKER"; then
            verify_owned
            if exists "$VOLUME/$GUARD"; then
                printf 'Prepared; an owned runtime attempt has been claimed. Results do not prove pairing success.\n'
            else
                printf 'Prepared; the temporary recovery attempt is armed.\n'
            fi
        else
            for name in "${FILES[@]}" "$GUARD"; do
                exists "$VOLUME/$name" && fail 'Unowned recovery files are present. Nothing was changed.'
            done
            printf 'Compatible card; recovery kit is not prepared.\n'
        fi ;;
esac
