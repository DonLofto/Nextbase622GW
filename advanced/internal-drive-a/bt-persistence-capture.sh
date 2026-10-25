#!/bin/sh
# Private observer only: no service, mount, internal-write or NAND operation.
printf 'Persistence observer entered.\n'
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
umask 077
sd=/tmp/SD0
fl=/tmp/FL0
pref=/pref
proc=/proc
guard=$sd/bt-persistence-capture.claimed
if [ -e "$guard" ] || [ -L "$guard" ]; then printf 'Already claimed; no writes.\n'; exit 0; fi
refuse() { printf 'Persistence observer refused: %s\n' "$1"; exit 20; }
[ -d "$sd" ] && [ ! -L "$sd" ] || refuse 'invalid SD directory'
token=$sd/usb.console
[ -f "$token" ] && [ ! -L "$token" ] || refuse 'missing regular USB token'
hash=$(sha256sum "$token" 2>/dev/null) || refuse 'cannot hash USB token'
[ "${hash%% *}" = 2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3 ] || refuse 'unknown USB token'
mkdir "$guard" || refuse 'cannot claim run'
n=1
while [ -e "$sd/bt-persistence-capture-$n" ] || [ -L "$sd/bt-persistence-capture-$n" ]; do n=$((n + 1)); done
out=$sd/bt-persistence-capture-$n
mkdir "$out" || refuse 'cannot create fresh results'
printf '%s\n' "$out" > "$guard/output.txt" || exit 30
mv "$token" "$out/usb.console.used" || refuse 'cannot retire USB token'

run_bounded() {
    label=$1 budget=$2; shift 2
    "$@" < /dev/null > "$out/$label.txt" 2>&1 &
    child=$! elapsed=0
    while /bin/kill -0 "$child" 2>/dev/null && [ "$elapsed" -lt "$budget" ]; do sleep 1; elapsed=$((elapsed + 1)); done
    if /bin/kill -0 "$child" 2>/dev/null; then
        printf 'TIMEOUT; partials may still change; no wait performed\n' > "$out/$label-status.txt"
        /bin/kill -TERM "$child" 2>/dev/null
        /bin/kill -KILL "$child" 2>/dev/null
        return 124
    fi
    wait "$child"; status=$?
    printf 'exit_status=%s\n' "$status" > "$out/$label-status.txt"
    return "$status"
}
collect() {
    failed=0
    {
        date; id; cat "$proc/uptime" "$proc/mounts" "$proc/self/mountinfo"
        printf 'mount_context_status=%s\n' "$?"
        ls -la "$fl" "$fl/pref" "$pref"
        printf 'directory_listing_status=%s\n' "$?"
        ps w
        for p in "$proc"/[0-9]*; do
            read -r comm < "$p/comm" 2>/dev/null || continue
            case "$comm" in amazon|amazon_app|bsa_server) printf '\n%s %s\n' "$p" "$comm"; readlink "$p/exe"; cat "$p/status" ;; esac
        done
    } > "$out/context.txt" 2>&1
    for f in "$fl/bt_config.xml" "$fl/bt_devices.xml" "$fl/si_devices.xml" "$pref/bt.conf"; do
        name=${f##*/}; statusfile=$out/$name.status.txt
        printf 'PENDING\n' > "$statusfile"
        if [ -L "$f" ]; then printf 'REFUSED_LINK\n' > "$statusfile"; failed=1; continue; fi
        if [ ! -e "$f" ]; then printf 'MISSING (optional)\n' > "$statusfile"; continue; fi
        if [ ! -f "$f" ]; then printf 'REFUSED_TYPE\n' > "$statusfile"; failed=1; continue; fi
        bytes=$(wc -c < "$f") || { printf 'SIZE_ERROR\n' > "$statusfile"; failed=1; continue; }
        if [ "$bytes" -gt 1048576 ]; then printf 'REFUSED_SIZE bytes=%s\n' "$bytes" > "$statusfile"; failed=1; continue; fi
        if ! dd if="$f" of="$out/$name.partial" bs=1024 count=1024 2> "$out/$name.copy-log.txt"; then printf 'COPY_ERROR\n' > "$statusfile"; failed=1; continue; fi
        actual=$(wc -c < "$out/$name.partial")
        if [ "$actual" != "$bytes" ]; then printf 'COPY_LENGTH_CHANGED\n' > "$statusfile"; failed=1; continue; fi
        mv "$out/$name.partial" "$out/$name" || { printf 'COPY_RENAME_ERROR\n' > "$statusfile"; failed=1; continue; }
        if sha256sum "$out/$name" > "$out/$name.sha256"; then printf 'COPIED bytes=%s\n' "$bytes" > "$statusfile"; else printf 'HASH_ERROR\n' > "$statusfile"; failed=1; fi
    done
    return "$failed"
}
run_bounded collect 20 collect
result=$?
printf 'collection_exit_status=%s\nRead-only observation; inspect context, per-file statuses and hashes.\nNo pairing or persistence success is established by this marker.\n' "$result" > "$out/RESULT.txt"
run_bounded sync-output 5 sync
sync_result=$?
printf 'sync_exit_status=%s\n' "$sync_result" >> "$out/RESULT.txt"
printf 'Persistence observer ended; inspect SD results.\n'
[ "$result" -eq 0 ] && [ "$sync_result" -eq 0 ]
