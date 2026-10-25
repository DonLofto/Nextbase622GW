#!/bin/sh
# 0.2.0: temporary RAM configuration and Amazon-only restart.
# Exit 0: attempt finished or an owned claim already exists; 20: refused;
# 30: attempt aborted. ATTEMPT_COMPLETE is not proof of phone pairing.
# util_svc mishandles empty stdout. Emit one bounded line before every guard
# and before redirecting detailed diagnostics to private result files.
printf 'Recovery kit 0.2.0: request received\n'
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
sd=/tmp/SD0
fl=/tmp/FL0
proc=/proc
guard=$sd/nb-bt-recovery.claimed
owner='Nextbase622GW Bluetooth Recovery Kit 0.2.0'
amazon=/usr/bin/amazon_app
bsa=/usr/bin/bsa_server
hcd=/usr/local/bcmdhd/bt.hcd

refuse() { printf 'Recovery refused: %s\n' "$1" >&2; exit 20; }
file_hash() {
    hash_result=$(sha256sum "$1" 2>/dev/null) || return 1
    printf '%s\n' "${hash_result%% *}"
}
regular_file() { [ -f "$1" ] && [ ! -L "$1" ]; }
owned_file() {
    regular_file "$1" &&
        [ "$(file_hash "$1")" = 751ae897679dde9d11e23fe0b7fd9204af1728cbbc3ab702e3af692a685a6194 ]
}

# A later boot must stop before logs, mkdir, sync, token removal or preflight.
if [ -e "$guard" ] || [ -L "$guard" ]; then
    if [ -d "$guard" ] && [ ! -L "$guard" ] && owned_file "$guard/owner.txt"; then
        exit 0
    fi
    refuse 'existing claim is not owned by this kit'
fi

# Read-only compatibility and ownership checks precede all SD mutations.
[ -d "$sd" ] && [ ! -L "$sd" ] || refuse 'SD mount is unavailable'
owned_file "$sd/nb-bt-recovery-kit.txt" || refuse 'ownership marker is absent or changed'
for managed in autoexec.ash nb-bt-recover.sh usb.console; do
    regular_file "$sd/$managed" || refuse 'an installed payload file is absent or a symlink'
done
[ "$(file_hash "$sd/usb.console")" = 2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3 ] ||
    refuse 'the verified diagnostic boot token is absent or changed'
[ "$(id -u)" = 0 ] || refuse 'root access is required'
[ "$(uname -m)" = armv7l ] && [ "$(uname -r)" = 4.9.76 ] || refuse 'unsupported Linux runtime'
for binary in "$amazon" "$bsa" "$hcd"; do
    regular_file "$binary" || refuse 'a required vendor file is absent or a symlink'
done
[ "$(file_hash "$amazon")" = ea1ad4c2969abffee176364eef67e5df24b37598de18862ab5866eb86b64b054 ] || refuse 'unsupported Amazon binary'
[ "$(file_hash "$bsa")" = 3fab6b79dc0becd8b4dd5f9c710989463661d6905f2e2e265d5a5377dea20747 ] || refuse 'unsupported BSA binary'
[ "$(file_hash "$hcd")" = 093bd3c261df7809ab30c77ca2d8d7870f5db66622d86d6125a17fd7295f6e55 ] || refuse 'unsupported controller firmware'
[ "$(readlink /tmp/amazon)" = "$amazon" ] || refuse 'unexpected Amazon launch path'
[ -d "$fl" ] && [ ! -L "$fl" ] || refuse 'unexpected internal-storage mountpoint'
awk -v target="$fl" '$1 == "a:" && $2 == target && $3 == "ambafs" { ok=1 } END { exit !ok }' "$proc/mounts" || refuse 'internal storage is not the expected AmbaFS mount'
awk '$2 == "/tmp" && $3 == "tmpfs" { ok=1 } END { exit !ok }' "$proc/mounts" || refuse 'temporary storage is not RAM backed'
for config in bt_config.xml bt_devices.xml si_devices.xml; do
    [ ! -L "$fl/$config" ] || refuse 'a configuration path is a symlink'
done

# A process name alone never authorizes a signal. Also refuse same-name
# processes from a different executable instead of creating duplicate clients.
scan_processes() {
    amazon_pids=
    bsa_pids=
    for process in "$proc"/[0-9]*; do
        [ -d "$process" ] || continue
        read -r comm < "$process/comm" 2>/dev/null || continue
        executable=$(readlink "$process/exe" 2>/dev/null) || continue
        pid=${process##*/}
        if [ "$executable" = "$amazon" ]; then
            amazon_pids="$amazon_pids $pid"
        elif [ "$executable" = "$bsa" ]; then
            bsa_pids="$bsa_pids $pid"
        else
            case "$comm" in amazon|amazon_app|bsa_server) return 1 ;; esac
        fi
    done
    return 0
}
scan_processes || refuse 'a Bluetooth process name belongs to an unexpected executable'
set -- $bsa_pids
[ "$#" -eq 1 ] || refuse 'exactly one compatible BSA process must already be running'
original_bsa=$1
set -- $amazon_pids
[ "$#" -eq 1 ] || refuse 'exactly one compatible Amazon process is required'
original_amazon=$1

# This conservative signature comes from the demonstrated failure. Missing
# XML or a zero MAC alone is insufficient. VCS is read with a fixed byte limit.
console=
symptom_observed=0
for console_device in /dev/vcs /dev/vcs1; do
    [ -r "$console_device" ] || continue
    console=$(dd if="$console_device" bs=4096 count=4 2>/dev/null) || continue
    case "$console" in
        *bt_config.xml*'Unable to Create defaul'*) symptom_observed=1; break ;;
        *) console= ;;
    esac
done
[ "$symptom_observed" -eq 1 ] || refuse 'the known default-configuration creation failure was not observed'

# Only this point arms an attempt. The claim contains owner.txt only; it is
# intentionally retained after any partial failure so later boots do not retry.
mkdir "$guard" || refuse 'could not acquire the one-shot claim'
printf '%s\n' "$owner" > "$guard/owner.txt" || exit 30
n=1
while [ -e "$sd/nb-bt-recovery-$n" ] || [ -L "$sd/nb-bt-recovery-$n" ]; do n=$((n + 1)); done
out=$sd/nb-bt-recovery-$n
mkdir "$out" || exit 30
exec 1>"$out/recovery.log" 2>&1
abort() {
    printf 'Attempt aborted: %s\n' "$1" > "$out/ABORTED.txt"
    printf 'ABORTED\n%s\nReboot removes any temporary RAM overlay.\n' "$1" > "$out/RESULT.txt"
    printf '%s\n' "$1"
    sync
    exit 30
}
date
id
cat "$proc/uptime" "$proc/mounts"
ps w
printf '%s\n' "$console" > "$out/failure-console.txt"
cp "$sd/autoexec.ash" "$out/autoexec.ash.source" || abort 'cannot preserve the installed hook'
# This is the verified trigger, already consumed by the RTOS mode validator.
mv "$sd/usb.console" "$out/usb.console.used" || abort 'cannot retire the owned console token'

ram=/tmp/nb-bt-recovery-$$
mkdir "$ram" || abort 'cannot create RAM configuration directory'
for config in bt_config.xml bt_devices.xml si_devices.xml; do
    if [ -f "$fl/$config" ]; then
        cp "$fl/$config" "$out/original-$config" && cp "$fl/$config" "$ram/$config" ||
            abort 'cannot preserve existing Bluetooth configuration'
    fi
done
# Global Linux mount: no mount-namespace tool is supplied by this firmware.
# This shadows the entire Linux /tmp/FL0 until reboot, without changing RTOS a:.
mount --bind "$ram" "$fl" > "$out/mount.txt" 2>&1 || abort 'RAM bind failed; services untouched'
cat "$proc/self/mountinfo" > "$out/mountinfo-after.txt"

[ "$(readlink "$proc/$original_bsa/exe" 2>/dev/null)" = "$bsa" ] || abort 'the original BSA process is no longer present'
scan_processes || abort 'Bluetooth process identity changed before stopping Amazon'
[ "$(readlink "$proc/$original_amazon/exe" 2>/dev/null)" = "$amazon" ] || abort 'Amazon process identity changed'
/bin/kill -TERM "$original_amazon" || abort 'cannot signal the exact Amazon process'
attempt=0
while [ "$attempt" -lt 5 ] && [ -d "$proc/$original_amazon" ]; do
    sleep 1
    attempt=$((attempt + 1))
done
if [ -d "$proc/$original_amazon" ]; then
    [ "$(readlink "$proc/$original_amazon/exe" 2>/dev/null)" = "$amazon" ] || abort 'PID identity changed after TERM'
    /bin/kill -KILL "$original_amazon" || abort 'cannot stop the exact Amazon process'
    sleep 1
fi
scan_processes || abort 'Bluetooth process identity changed after stopping Amazon'
[ -z "$amazon_pids" ] || abort 'an old Amazon process remains; no new instance started'
[ "$(readlink "$proc/$original_bsa/exe" 2>/dev/null)" = "$bsa" ] || abort 'BSA exited; no reset attempted'

cd /tmp || abort 'cannot enter the Bluetooth working directory'
/tmp/amazon </dev/null > "$out/amazon.log" 2>&1 &
new_pid=$!
printf '%s\n' "$new_pid" > "$out/amazon.pid"
elapsed=0
for delay in 5 15; do
    sleep "$delay"
    elapsed=$((elapsed + delay))
    {
        date
        cat "$proc/uptime"
        ps w
        ls -la "$fl"
        cat "$fl/bt_config.xml"
    } > "$out/state-after-$elapsed.txt" 2>&1
done
for config in bt_config.xml bt_devices.xml si_devices.xml; do
    if [ -f "$ram/$config" ]; then cp "$ram/$config" "$out/$config"; fi
done
dmesg > "$out/dmesg.txt" 2>&1
printf 'Attempt finished. RAM overlay and Amazon remain active until reboot. Check phone pairing independently.\n' > "$out/ATTEMPT_COMPLETE.txt"
printf 'ATTEMPT_COMPLETE\nCheck phone pairing independently; this marker does not establish success.\nRAM configuration is temporary and disappears on reboot.\n' > "$out/RESULT.txt"
sync
exit 0
