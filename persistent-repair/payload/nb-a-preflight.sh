#!/bin/sh
# Read-only identity/fault preflight, followed by the frozen A capture wrapper.
# 20: refused before SD output; 30: incomplete proof, so backup was not started.
printf 'Drive A preflight entered.\n'
PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PATH
umask 077
sd=/tmp/SD0
fl=/tmp/FL0
proc=/proc
amazon=/usr/bin/amazon_app
bsa=/usr/bin/bsa_server
hcd=/usr/local/bcmdhd/bt.hcd
script=$sd/nb-a-preflight.sh
hook=$sd/autoexec.ash
backup=$sd/bt-nand-backup.sh
out=$sd/nb-a-preflight

# util_svc exposes stdout only; fixed, nonsensitive reasons keep RPC under 511 bytes.
refuse() { printf 'Drive A preflight refused: %s\n' "$1"; exit 20; }
incomplete() { printf 'Drive A preflight incomplete: %s\n' "$1"; exit 30; }
regular() { [ -f "$1" ] && [ ! -L "$1" ]; }
file_hash() {
    value=$(sha256sum "$1" 2>/dev/null) || return 1
    value=${value%% *}
    [ "${#value}" -eq 64 ] || return 1
    case "$value" in *[!0-9a-f]*) return 1 ;; esac
    printf '%s\n' "$value"
}

# Every existing output/claim blocks replay, including dangling links.
for path in "$out" "$sd/bt-nand-backup.claimed"; do
    [ ! -e "$path" ] && [ ! -L "$path" ] || refuse 'existing result or backup claim'
done
[ -d "$sd" ] && [ ! -L "$sd" ] || refuse 'invalid SD directory'
[ -d "$fl" ] && [ ! -L "$fl" ] || refuse 'invalid internal storage path'
[ "$(id -u)" = 0 ] || refuse 'root is required'
[ "$(uname -m)" = armv7l ] && [ "$(uname -r)" = 4.9.76 ] || refuse 'unsupported Linux runtime'
for path in "$sd/Nextbase.info" "$script" "$hook" "$backup" "$sd/usb.console" "$amazon" "$bsa" "$hcd"; do
    regular "$path" || refuse 'a required staged or vendor file is absent or linked'
done
[ "$(wc -c < "$sd/Nextbase.info")" -le 1048576 ] || refuse 'camera identity is unexpectedly large'
awk '
    tolower($0) ~ /^[[:space:]]*model[[:space:]]*:/ { m++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/[[:space:]]*$/, "", value); model=value }
    tolower($0) ~ /^[[:space:]]*firmware[[:space:]]*:/ { f++; value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/[[:space:]]*$/, "", value); firmware=value }
    END { exit !(m == 1 && f == 1 && model == "622GW" && firmware == "R13.3") }
' "$sd/Nextbase.info" || refuse 'unsupported or ambiguous model/firmware'
for path in "$sd"/*; do
    lower=$(printf '%s' "${path##*/}" | tr 'A-Z' 'a-z')
    case "$lower" in fw*.bin|ld*.bin) refuse 'firmware update files are present' ;; esac
done
[ "$(file_hash "$sd/usb.console")" = 2b19515c1ee1515adc54d58c62cac67679ad3493185cddfe92e5872a5a8527f3 ] || refuse 'unknown USB token'
[ "$(file_hash "$backup")" = 32c4ccbdbb44d89cf5e6e122270c6c6d568c2efa623960c55a14006ccc53f365 ] || refuse 'backup wrapper differs from the frozen asset'
amazon_hash=$(file_hash "$amazon") || refuse 'cannot hash Amazon binary'
bsa_hash=$(file_hash "$bsa") || refuse 'cannot hash BSA binary'
hcd_hash=$(file_hash "$hcd") || refuse 'cannot hash controller firmware'
[ "$amazon_hash" = ea1ad4c2969abffee176364eef67e5df24b37598de18862ab5866eb86b64b054 ] || refuse 'unsupported Amazon binary'
[ "$bsa_hash" = 3fab6b79dc0becd8b4dd5f9c710989463661d6905f2e2e265d5a5377dea20747 ] || refuse 'unsupported BSA binary'
[ "$hcd_hash" = 093bd3c261df7809ab30c77ca2d8d7870f5db66622d86d6125a17fd7295f6e55 ] || refuse 'unsupported controller firmware'
[ "$(readlink /tmp/amazon)" = "$amazon" ] || refuse 'unexpected Amazon launch path'
for name in bt_config.xml bt_devices.xml si_devices.xml; do
    [ ! -L "$fl/$name" ] || refuse 'a configuration path is linked'
done
mounts=$(cat "$proc/mounts") || refuse 'cannot read mounts'
printf '%s\n' "$mounts" | awk -v target="$fl" '
    $2 == target { n++; if ($1 != "a:" || $3 != "ambafs") bad=1 }
    END { exit !(n == 1 && !bad) }
' || refuse 'internal storage is not one genuine A-backed AmbaFS mount'
printf '%s\n' "$mounts" | awk '
    $2 == "/tmp" { n++; if ($3 != "tmpfs") bad=1 }
    END { exit !(n == 1 && !bad) }
' || refuse 'temporary storage is not RAM backed'

# Read only a bounded VCS window. A failed partial read cannot authorize output.
console_device=
for candidate in /dev/vcs /dev/vcs1; do
    [ -r "$candidate" ] || continue
    console=$(dd if="$candidate" bs=4096 count=4 2>/dev/null) || continue
    case "$console" in
        *bt_config.xml*'Unable to Create defaul'*) console_device=$candidate; break ;;
    esac
done
[ -n "$console_device" ] || refuse 'known default-configuration creation failure was not observed'
identity_hash=$(file_hash "$sd/Nextbase.info") || refuse 'cannot hash camera identity'
script_hash=$(file_hash "$script") || refuse 'cannot hash preflight source'
hook_hash=$(file_hash "$hook") || refuse 'cannot hash startup hook'

# All compatibility/fault checks above are read-only. Preserve raw evidence now.
mkdir "$out" || refuse 'cannot exclusively create preflight output'
dd if="$console_device" of="$out/failure-console.bin" bs=4096 count=4 2>/dev/null || incomplete 'cannot preserve failure evidence'
length=$(wc -c < "$out/failure-console.bin")
[ "$length" -gt 0 ] && [ "$length" -le 16384 ] || incomplete 'invalid failure evidence length'
proof=$(cat "$out/failure-console.bin") || incomplete 'cannot reread failure evidence'
case "$proof" in
    *bt_config.xml*'Unable to Create defaul'*) ;;
    *) incomplete 'failure evidence changed before preservation' ;;
esac
printf '%s\n' "$mounts" > "$out/mounts.txt" || incomplete 'cannot preserve mounts'
{
    printf 'PREFLIGHT_VERIFIED\nmodel=622GW\nfirmware=R13.3\nmachine=armv7l\nkernel=4.9.76\n'
    printf 'amazon_sha256=%s\nbsa_sha256=%s\nhcd_sha256=%s\n' "$amazon_hash" "$bsa_hash" "$hcd_hash"
    printf 'identity_sha256=%s\nscript_sha256=%s\nhook_sha256=%s\n' "$identity_hash" "$script_hash" "$hook_hash"
    printf 'fl_mount=ambafs_a\nfailure=BT_DEFAULT_CONFIG_CREATE_FAILED\n'
} > "$out/RESULT.txt" || incomplete 'cannot preserve verification result'
(cd "$out" && sha256sum RESULT.txt failure-console.bin mounts.txt > SHA256SUMS) || incomplete 'cannot hash proof files'
[ "$(wc -l < "$out/SHA256SUMS")" -eq 3 ] || incomplete 'incomplete proof manifest'
sync || incomplete 'proof sync failed'
[ "$(file_hash "$backup")" = 32c4ccbdbb44d89cf5e6e122270c6c6d568c2efa623960c55a14006ccc53f365 ] || incomplete 'backup wrapper changed before execution'
exec /bin/sh "$backup"
