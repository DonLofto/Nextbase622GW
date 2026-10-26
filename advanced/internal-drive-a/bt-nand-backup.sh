#!/bin/sh
# Private read-only DRIVE_A capture. Never a full-chip or restorable backup.
# Execute only after separate staging/helper review; no RTOS filesystem query.
printf 'NAND capture wrapper entered.\n'
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
LC_ALL=C
export LC_ALL
umask 077
sd=/tmp/SD0
proc=/proc
sys=/sys
tmp=/tmp
node=/dev/mtd9ro
guard=$sd/bt-nand-backup.claimed
helper=$sd/nb-mtd-readonly
manifest=$sd/nb-mtd-readonly.sha256
source=$sd/bt-nand-backup.sh
trigger=$sd/usb.console

# Every existing claim, including partial/unknown claims, blocks another run.
if [ -e "$guard" ] || [ -L "$guard" ]; then
    printf 'Already claimed; no writes or reads attempted.\n'
    exit 0
fi
refuse() { printf 'NAND capture refused: %s\n' "$1"; exit 20; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
file_hash() {
    value=$(sha256sum "$1" 2>/dev/null) || return 1
    printf '%s\n' "${value%% *}"
}

# These checks are read-only and precede any SD output or one-shot claim.
[ -d "$sd" ] && [ ! -L "$sd" ] || refuse 'invalid SD directory'
[ -d "$tmp" ] && [ ! -L "$tmp" ] || refuse 'invalid RAM directory'
[ "$(id -u)" = 0 ] || refuse 'root is required'
[ "$(uname -m)" = armv7l ] || refuse 'unsupported CPU architecture'
awk -v target="$tmp" '$2 == target && $3 == "tmpfs" { found=1 } END { exit !found }' "$proc/mounts" || refuse 'temporary directory is not RAM backed'
regular "$sd/Nextbase.info" || refuse 'missing regular camera identity'
awk '
    tolower($0) ~ /^[[:space:]]*model[[:space:]]*:/ { m++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/[[:space:]]*$/, "", value); model=value }
    tolower($0) ~ /^[[:space:]]*firmware[[:space:]]*:/ { f++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/[[:space:]]*$/, "", value); firmware=value }
    END { exit !(m == 1 && f == 1 && model == "622GW" && length(firmware) <= 64 && firmware ~ /^[[:print:]]+$/) }
' "$sd/Nextbase.info" || refuse 'unsupported or ambiguous model/firmware'
for path in "$sd"/*; do
    name=${path##*/}
    lower=$(printf '%s' "$name" | tr 'A-Z' 'a-z')
    case "$lower" in fw*.bin|ld*.bin) refuse 'firmware update files are present' ;; esac
done
regular "$trigger" || refuse 'missing regular USB token'
[ "$(file_hash "$trigger")" = 2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3 ] || refuse 'unknown USB token'
for path in "$source" "$helper" "$manifest" "$sd/autoexec.ash"; do
    regular "$path" || refuse 'missing or linked staged source/helper/provenance'
done
[ "$(wc -l < "$manifest")" -eq 1 ] 2>/dev/null || refuse 'helper manifest must have exactly one line'
read -r expected_helper helper_name extra < "$manifest" || refuse 'unreadable helper manifest'
[ "$helper_name" = nb-mtd-readonly ] && [ -z "$extra" ] && [ "${#expected_helper}" -eq 64 ] || refuse 'malformed helper manifest'
case "$expected_helper" in *[!0-9a-fA-F]*) refuse 'malformed helper digest' ;; esac
expected_helper=$(printf '%s' "$expected_helper" | tr 'A-F' 'a-f')
actual_helper=$(file_hash "$helper") || refuse 'cannot hash source helper'
[ "$actual_helper" = "$expected_helper" ] || refuse 'source helper hash mismatch'
source_hash=$(file_hash "$source") || refuse 'cannot hash wrapper source'
hook_hash=$(file_hash "$sd/autoexec.ash") || refuse 'cannot hash startup hook'

awk '
    $4 == "\"DRIVE_A\"" { matches++; if ($1 != "mtd9:" || tolower($2) != "00b80000" || tolower($3) != "00020000") bad=1 }
    END { exit !(matches == 1 && !bad) }
' "$proc/mtd" || refuse 'proc MTD identity/geometry differs from reviewed DRIVE_A'
directory=$sys/class/mtd/mtd9
[ -d "$directory" ] || refuse 'missing selected sysfs partition'
for field_value in name:DRIVE_A type:nand size:12058624 erasesize:131072 writesize:2048 oobsize:128 offset:203685888 flags:0x400 dev:90:18 ecc_strength:8 ecc_step_size:512 bitflip_threshold:6; do
    field=${field_value%%:*}
    expected=${field_value#*:}
    [ "$(cat "$directory/$field" 2>/dev/null)" = "$expected" ] || refuse 'sysfs DRIVE_A identity/geometry differs'
done
[ -c "$node" ] && [ ! -L "$node" ] || refuse 'read-only MTD character node missing or linked'
# Shipped BusyBox has no stat applet. The helper independently fstat64-checks
# this fixed node as character device 90:19 before any NAND data read.

mkdir "$guard" 2>/dev/null || refuse 'cannot claim one-shot run'
n=1
while [ -e "$sd/bt-nand-backup-$n" ] || [ -L "$sd/bt-nand-backup-$n" ]; do n=$((n + 1)); done
out=$sd/bt-nand-backup-$n
mkdir "$out" 2>/dev/null || refuse 'cannot create fresh output directory'
printf '%s\n' "$out" > "$guard/output.txt" || exit 30
exec 2> "$out/wrapper-errors.txt"

finish() {
    state=$1 reason=$2 code=$3
    {
        printf '%s\nreason=%s\n' "$state" "$reason"
        printf 'restorable_nand_backup=no\nfull_nand_backup=no\n'
        printf 'Only the selected DRIVE_A partition was requested; no repair or internal write was attempted.\n'
        printf 'A timed-out child may remain until reboot; its partial files may still change.\n'
    } > "$out/RESULT.txt" || exit 30
    printf 'Wrapper reached its final step; inspect RESULT.txt and per-command statuses.\n' > "$out/CAPTURE_FINISHED.txt" || exit 30
    printf 'NAND capture wrapper ended; inspect SD result files.\n'
    exit "$code"
}

# Redirect all child descriptors away from RPC. A task stuck in kernel I/O can
# survive signals; never wait after expiry or hash its still-mutable output.
run_bounded() {
    label=$1 budget=$2
    shift 2
    "$@" < /dev/null > "$out/$label.txt" 2>&1 &
    child=$!
    elapsed=0
    while /bin/kill -0 "$child" 2>/dev/null && [ "$elapsed" -lt "$budget" ]; do
        sleep 1
        elapsed=$((elapsed + 1))
    done
    if /bin/kill -0 "$child" 2>/dev/null; then
        printf 'TIMEOUT pid=%s budget_seconds=%s; no wait performed\n' "$child" "$budget" > "$out/$label-status.txt"
        cat "$proc/$child/status" "$proc/$child/wchan" > "$out/$label-timeout-process.txt" 2>&1
        /bin/kill -TERM "$child" 2>/dev/null
        /bin/kill -KILL "$child" 2>/dev/null
        if /bin/kill -0 "$child" 2>/dev/null; then
            printf 'MAY_STILL_BE_RUNNING; partial files may still change\n' >> "$out/$label-status.txt"
        fi
        return 124
    fi
    wait "$child"
    status=$?
    printf 'exit_status=%s\n' "$status" > "$out/$label-status.txt"
    return "$status"
}

sysfs_snapshot() {
    for field in name type size erasesize writesize oobsize offset flags dev ecc_strength ecc_step_size bitflip_threshold corrected_bits ecc_failures bad_blocks bbt_blocks; do
        printf '%s=' "$field"
        cat "$directory/$field" || return 1
    done
}
local_snapshot() {
    date || return 1
    id || return 1
    for path in "$proc/uptime" "$proc/cmdline" "$proc/mounts" "$proc/self/mountinfo" "$proc/mtd"; do
        printf '\n%s\n' "$path"
        cat "$path" || return 1
    done
}

cp "$source" "$out/bt-nand-backup.sh.source" && cp "$sd/autoexec.ash" "$out/autoexec.ash.source" && cp "$manifest" "$out/nb-mtd-readonly.sha256.source" || finish NOT_ATTEMPTED 'cannot preserve staged sources' 30
[ "$(file_hash "$out/bt-nand-backup.sh.source")" = "$source_hash" ] && [ "$(file_hash "$out/autoexec.ash.source")" = "$hook_hash" ] || finish NOT_ATTEMPTED 'source copy verification failed' 30
[ "$(file_hash "$trigger")" = 2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3 ] || finish NOT_ATTEMPTED 'USB token changed before retirement' 30
[ ! -e "$out/usb.console.used" ] && [ ! -L "$out/usb.console.used" ] || finish NOT_ATTEMPTED 'USB token destination already exists' 30
# The result directory was exclusively created by this run. Plain mv is
# supported by the shipped applet; its optional -n flag is not assumed.
mv "$trigger" "$out/usb.console.used" || finish NOT_ATTEMPTED 'cannot retire owned USB token' 30
[ ! -e "$trigger" ] && [ ! -L "$trigger" ] || finish NOT_ATTEMPTED 'USB token retirement collision' 30

ram=$tmp/nb-mtd-readonly-$$
mkdir "$ram" || finish NOT_ATTEMPTED 'cannot create exclusive RAM helper directory' 30
run_bounded helper-copy 10 cp "$helper" "$ram/nb-mtd-readonly" || finish NOT_ATTEMPTED 'RAM helper copy failed or timed out' 30
chmod 700 "$ram/nb-mtd-readonly" || finish NOT_ATTEMPTED 'cannot make RAM helper executable' 30
ram_hash=$(file_hash "$ram/nb-mtd-readonly") || finish NOT_ATTEMPTED 'cannot hash RAM helper' 30
[ "$ram_hash" = "$expected_helper" ] || finish NOT_ATTEMPTED 'RAM helper hash mismatch' 30
{
    printf 'source=%s\nsource_sha256=%s\nram_executable=%s\nram_sha256=%s\n' "$helper" "$actual_helper" "$ram/nb-mtd-readonly" "$ram_hash"
    printf 'wrapper_sha256=%s\nautoexec_sha256=%s\n' "$source_hash" "$hook_hash"
    printf 'Source helper remains in SD root; no duplicate binary is stored in this result directory.\n'
} > "$out/helper-provenance.txt" || finish NOT_ATTEMPTED 'cannot preserve helper provenance' 30

run_bounded local-before 10 local_snapshot || finish NOT_ATTEMPTED 'local metadata snapshot failed' 30
run_bounded sysfs-before 10 sysfs_snapshot || finish NOT_ATTEMPTED 'sysfs before snapshot failed' 30
run_bounded dmesg-before 10 dmesg || finish NOT_ATTEMPTED 'kernel before snapshot failed' 30
run_bounded helper-read 120 "$ram/nb-mtd-readonly" "$out"
helper_status=$?
metadata_ok=1
run_bounded local-after 10 local_snapshot || metadata_ok=0
run_bounded sysfs-after 10 sysfs_snapshot || metadata_ok=0
run_bounded dmesg-after 10 dmesg || metadata_ok=0
[ "$helper_status" -ne 124 ] || finish PARTIAL_OR_UNVERIFIED 'helper timed out; outputs retained without hashing' 30
[ "$helper_status" -eq 0 ] || finish PARTIAL_OR_UNVERIFIED 'helper reported refusal or incomplete capture; outputs retained' 30
[ "$metadata_ok" -eq 1 ] || finish PARTIAL_OR_UNVERIFIED 'after metadata snapshot failed' 30

for name in DRIVE_A-corrected-main.bin DRIVE_A-raw-main.bin DRIVE_A-raw-oob.bin DRIVE_A-badblocks.tsv read-status.tsv helper-summary.txt helper-ecc-before.txt helper-ecc-after.txt; do
    regular "$out/$name" && [ -s "$out/$name" ] || finish PARTIAL_OR_UNVERIFIED 'a required helper artifact is missing, linked or empty' 30
done
[ "$(wc -c < "$out/DRIVE_A-corrected-main.bin")" -eq 12058624 ] && [ "$(wc -c < "$out/DRIVE_A-raw-main.bin")" -eq 12058624 ] && [ "$(wc -c < "$out/DRIVE_A-raw-oob.bin")" -eq 753664 ] || finish PARTIAL_OR_UNVERIFIED 'capture length differs from exact reviewed geometry' 30
awk -F '\t' '
    NR == 1 { if ($0 != "offset\tis_bad\terrno") bad=1; next }
    NF != 3 || $1 !~ /^[0-9]+$/ || $2 !~ /^[01]$/ || $3 != 0 { bad=1 }
    { if ($1 != n * 131072) bad=1; n++ }
    END { exit !(n == 92 && !bad) }
' "$out/DRIVE_A-badblocks.tsv" || finish PARTIAL_OR_UNVERIFIED 'bad-block map coverage or query status differs' 30
awk -F '\t' '
    NR == 1 { if ($0 != "component\toffset\trequested\treturned\terrno\tcorrected_bits\tecc_failures") bad=1; next }
    NF != 7 || $2 !~ /^[0-9]+$/ || $3 !~ /^[0-9]+$/ || $4 !~ /^[0-9]+$/ || $5 != 0 || $6 !~ /^[0-9]+$/ || $7 != 0 { bad=1 }
    $1 == "corrected-main" { if ($2 != corrected * 65536 || $3 != 65536 || $4 != 65536) bad=1; corrected++; next }
    $1 == "raw-main" { if ($2 != raw * 65536 || $3 != 65536 || $4 != 65536) bad=1; raw++; next }
    $1 == "raw-oob" { if ($2 != oob * 2048 || $3 != 128 || $4 != 128) bad=1; oob++; next }
    { bad=1 }
    END { exit !(corrected == 184 && raw == 184 && oob == 5888 && !bad) }
' "$out/read-status.tsv" || finish PARTIAL_OR_UNVERIFIED 'page-read status/length/coverage differs' 30
awk -F '=' '
    BEGIN { expected["errno"]="0"; expected["corrected_main_bytes"]="12058624"; expected["raw_main_bytes"]="12058624"; expected["raw_oob_bytes"]="753664"; expected["badblock_records"]="92"; expected["ecc_failures_before"]="0"; expected["ecc_failures_after"]="0"; expected["restorable_nand_backup"]="no"; expected["full_nand_backup"]="no" }
    NR == 1 { if ($0 != "COMPLETE") bad=1; next }
    $1 in expected { seen[$1]++; if (NF != 2 || $2 != expected[$1]) bad=1 }
    END { for (key in expected) if (seen[key] != 1) bad=1; exit bad }
' "$out/helper-summary.txt" || finish PARTIAL_OR_UNVERIFIED 'helper summary does not establish all expected components' 30

run_bounded capture-hashes 20 sha256sum "$out/DRIVE_A-corrected-main.bin" "$out/DRIVE_A-raw-main.bin" "$out/DRIVE_A-raw-oob.bin" "$out/DRIVE_A-badblocks.tsv" "$out/read-status.tsv" "$out/helper-summary.txt" "$out/helper-ecc-before.txt" "$out/helper-ecc-after.txt" || finish PARTIAL_OR_UNVERIFIED 'capture hashing failed or timed out' 30
cp "$out/capture-hashes.txt" "$out/capture.sha256" || finish PARTIAL_OR_UNVERIFIED 'cannot preserve capture hashes' 30
[ "$(wc -l < "$out/capture.sha256")" -eq 8 ] || finish PARTIAL_OR_UNVERIFIED 'capture hash record is incomplete' 30
run_bounded verify-hashes 20 sha256sum -c "$out/capture.sha256" || finish PARTIAL_OR_UNVERIFIED 'capture hashes did not verify' 30
run_bounded sync-output 5 sync || finish PARTIAL_OR_UNVERIFIED 'output sync failed or timed out' 30
finish PARTITION_CAPTURE_VERIFIED 'all selected-partition components, statuses, lengths and hashes verified' 0
