#!/bin/sh
# Local build only; does not run or stage the ARM executable or install tools.
set -eu
task_source_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
task_build_dir=${1:-/tmp/622gw-mtd-readonly-build}
task_clang=${NB_MTD_CLANG:-/opt/homebrew/opt/llvm@21/bin/clang}
task_linker=${NB_MTD_LINKER:-$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/lib/rustlib/aarch64-apple-darwin/bin/rust-lld}
task_linker_lib=${NB_MTD_LINKER_LIB:-$HOME/.rustup/toolchains/stable-aarch64-apple-darwin/lib}
[ -x "$task_clang" ] && [ -x "$task_linker" ] || { printf 'Existing Clang/LLD required; nothing installed.\n' >&2; exit 1; }
mkdir -p "$task_build_dir"
task_build_dir=$(CDPATH= cd "$task_build_dir" && pwd)
task_object=$task_build_dir/nb-mtd-readonly.o
task_binary=$task_build_dir/nb-mtd-readonly
"$task_clang" --target=armv7-linux-gnueabi -mcpu=cortex-a53 -marm -mfloat-abi=soft \
    -Os -std=c11 -Wall -Wextra -Werror -ffreestanding -fno-builtin \
    -fno-stack-protector -fno-unwind-tables -fno-asynchronous-unwind-tables \
    -fno-pic -fno-ident -c "$task_source_dir/nb-mtd-readonly.c" -o "$task_object"
DYLD_LIBRARY_PATH="$task_linker_lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" \
    "$task_linker" -flavor gnu -m armelf_linux_eabi -static --no-dynamic-linker \
    -e _start --build-id=none --strip-all -o "$task_binary" "$task_object"
chmod 755 "$task_binary"
{
    printf 'source='; shasum -a 256 "$task_source_dir/nb-mtd-readonly.c"
    printf 'build_script='; shasum -a 256 "$task_source_dir/build-nb-mtd-readonly.sh"
    "$task_clang" --version
    DYLD_LIBRARY_PATH="$task_linker_lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}" "$task_linker" -flavor gnu --version
} > "$task_build_dir/build-provenance.txt"
(CDPATH= cd "$task_build_dir" && shasum -a 256 nb-mtd-readonly > nb-mtd-readonly.sha256)
printf 'Built only: %s\n' "$task_binary"
cat "$task_build_dir/nb-mtd-readonly.sha256"
