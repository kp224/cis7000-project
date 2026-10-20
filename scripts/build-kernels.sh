#!/usr/bin/env bash
# Build both full kernels on the x86-64 CloudLab node; does not install them.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$project_root/configs/kernel-source.env"
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
    echo 'Run this on the x86-64 Linux test node.' >&2; exit 1;
}
jobs=${JOBS:-8}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || { echo 'JOBS must be positive.' >&2; exit 1; }
# Keep m510 as the default; select the additional model explicitly.
node_type=${NODE_TYPE:-m510}
case "$node_type" in
    m510) drivers=(BLK_DEV_NVME MLX4_EN) ;;
    c6525-25g) drivers=(SATA_AHCI SCSI BLK_DEV_SD MLX5_CORE MLX5_CORE_EN) ;;
    *) echo "Unsupported NODE_TYPE: $node_type" >&2; exit 1 ;;
esac
common="$project_root/work/kernel-config"
results="$project_root/results/cloudlab-build"
mkdir -p "$common" "$results"

for variant in eevdf cfs; do
    tree="$project_root/work/linux-$variant"
    status=$(git -C "$tree" status --porcelain)
    [[ -z "$status" && -f "$tree/Makefile" ]] || {
        echo "$tree must be clean and fully checked out." >&2; exit 1;
    }
done
[[ $(git -C "$project_root/work/linux-eevdf" rev-parse HEAD) == "$LINUX_COMMIT" ]]
[[ $(git -C "$project_root/work/linux-cfs" rev-parse 'HEAD^{tree}') == \
    2519def936d64df42abe40b623249424845e5e6c ]]

# Derive the shared config once, retaining this node's loaded drivers.
config="$common/ready.config"
if [[ ! -f "$config" ]]; then
    cp "/boot/config-$(uname -r)" "$results/seed.config"
    cp "$results/seed.config" "$common/.config"
    lsmod > "$results/lsmod.txt"
    tree="$project_root/work/linux-eevdf"
    make -C "$tree" O="$common" LOCALVERSION= olddefconfig
    make -C "$tree" O="$common" LOCALVERSION= \
        LSMOD="$results/lsmod.txt" localmodconfig </dev/null
    "$tree/scripts/config" --file "$common/.config" \
        --disable DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT --disable DEBUG_INFO_DWARF4 \
        --disable DEBUG_INFO_DWARF5 --disable DEBUG_INFO_BTF \
        --disable DEBUG_INFO_BTF_MODULES --enable DEBUG_INFO_NONE \
        --set-str SYSTEM_TRUSTED_KEYS '' --set-str SYSTEM_REVOCATION_KEYS '' \
        --disable MODULE_SIG --disable LOCALVERSION_AUTO \
        --enable SCHED_DEBUG --enable SCHEDSTATS
    make -C "$tree" O="$common" LOCALVERSION= olddefconfig
    config="$common/.config"
fi

# Check cached configs too, so changing NODE_TYPE cannot skip driver checks.
for key in "${drivers[@]}" EXT4_FS SERIAL_8250_CONSOLE EFI BLK_DEV_INITRD NFS_FS; do
    grep -Eq "^CONFIG_${key}=[ym]$" "$config" || {
        echo "Missing required driver for $node_type: CONFIG_$key" >&2; exit 1;
    }
done
if [[ "$config" != "$common/ready.config" ]]; then
    cp "$config" "$common/ready.config"
fi
printf '%s\n' "$node_type" > "$results/node-type.txt"
gcc --version > "$results/compiler.txt"
for variant in eevdf cfs; do
    tree="$project_root/work/linux-$variant"
    out="$project_root/work/build-$variant"
    mkdir -p "$out"
    cp "$common/ready.config" "$out/.config"
    "$tree/scripts/config" --file "$out/.config" --set-str LOCALVERSION "-cis7000-$variant"
    make -C "$tree" O="$out" LOCALVERSION= olddefconfig
    release=$(make -s -C "$tree" O="$out" LOCALVERSION= kernelrelease)
    [[ $release == "6.6.0-cis7000-$variant" ]]
    cp "$out/.config" "$results/$variant.config"
    make -C "$tree" O="$out" LOCALVERSION= -j"$jobs" bzImage modules \
        2>&1 | tee "$results/$variant.log"
    printf '%s\n' "$release" > "$results/$variant.release"
done
diff -u <(grep -v '^CONFIG_LOCALVERSION=' "$results/eevdf.config") \
    <(grep -v '^CONFIG_LOCALVERSION=' "$results/cfs.config")
echo 'Both kernels built with matching configs (apart from their release names).'
