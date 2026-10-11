#!/usr/bin/env bash
# Install this CloudLab node's two test kernels without changing its default.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
results="$project_root/results/cloudlab-install"
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || exit 1
original=$(uname -r)
[[ $original != 6.6.0-cis7000-* ]] || { echo 'Boot the original kernel first.' >&2; exit 1; }
for command in python3 make mkinitramfs grub-script-check sha256sum install; do
    command -v "$command" >/dev/null
done
[[ -d "/lib/modules/$original" && -s "/boot/vmlinuz-$original" &&
   -s "/boot/initrd.img-$original" && -s /boot/grub/grub.cfg ]]
[[ ! -e /boot/grub/custom.cfg && ! -L /boot/grub/custom.cfg ]] || {
    echo 'Existing custom.cfg: refusing to overwrite.' >&2; exit 1;
}
for variant in eevdf cfs; do
    tree="$project_root/work/linux-$variant"
    out="$project_root/work/build-$variant"
    release="6.6.0-cis7000-$variant"
    [[ -s "$out/arch/x86/boot/bzImage" && -s "$out/System.map" &&
       -s "$out/.config" && -s "$out/modules.order" && -s "$out/modules.builtin" ]]
    [[ $(cat "$project_root/results/cloudlab-build/$variant.release") == "$release" ]]
    [[ $(make -s -C "$tree" O="$out" LOCALVERSION= kernelrelease) == "$release" ]]
    cmp "$out/.config" "$project_root/results/cloudlab-build/$variant.config"
    while IFS= read -r module; do
        [[ -s "$out/$module" ]] || { echo "Missing built module: $module" >&2; exit 1; }
    done < "$out/modules.order"
    for target in "/lib/modules/$release" "/boot/vmlinuz-$release" \
        "/boot/System.map-$release" "/boot/config-$release" "/boot/initrd.img-$release"; do
        [[ ! -e "$target" && ! -L "$target" ]] || {
            echo "Existing target: $target; refusing to overwrite." >&2; exit 1;
        }
    done
done
diff -u <(grep -v '^CONFIG_LOCALVERSION=' "$project_root/work/build-eevdf/.config") \
    <(grep -v '^CONFIG_LOCALVERSION=' "$project_root/work/build-cfs/.config")
mkdir -p "$results"
staging=$(mktemp -d "$results/staging.XXXXXX")
sudo -n cat /boot/grub/grub.cfg > "$staging/grub.cfg.original"
sudo -n sha256sum /boot/grub/grub.cfg "/boot/vmlinuz-$original" "/boot/initrd.img-$original" \
    > "$staging/original.sha256"
# Copy the actual working entry, preserving its device search and console setup.
python3 - "$staging/grub.cfg.original" "$staging/custom.cfg" "$original" <<'PY'
import pathlib, re, sys
source, destination, original = sys.argv[1:]
text = pathlib.Path(source).read_text()
if not re.search(r'^\s*source\s+\$\{config_directory\}/custom\.cfg\s*$', text, re.M):
    raise SystemExit('Existing GRUB configuration does not source custom.cfg')
entries = list(re.finditer(r"^menuentry\s+['\"]Ubuntu['\"][^\n]*\{\n(.*?)^\}", text, re.M | re.S))
if len(entries) != 1:
    raise SystemExit('Expected exactly one top-level Ubuntu entry')
body = entries[0].group(1)
linux = list(re.finditer(r'^(\s*linux\s+)(\S+)([^\n]*)$', body, re.M))
initrd = list(re.finditer(r'^(\s*initrd\s+)(\S+)(\s*)$', body, re.M))
if len(linux) != 1 or len(initrd) != 1:
    raise SystemExit('Expected one linux line and one single-image initrd line')
if linux[0].group(2) != '/boot/vmlinuz-' + original or initrd[0].group(2) != '/boot/initrd.img-' + original:
    raise SystemExit('Ubuntu entry does not boot the verified original artifacts')
args = linux[0].group(3)
running_args = pathlib.Path('/proc/cmdline').read_text().split()
if not all(word in running_args for word in args.split()):
    raise SystemExit('GRUB arguments differ from the running recovery kernel')
if not any(word.startswith('root=') for word in args.split()):
    raise SystemExit('The working entry has no root filesystem argument')
args = ' ' + ' '.join(word for word in args.split() if not word.startswith('panic=')) + ' panic=30'
output = ['# CIS7000 test kernels; original grub.cfg and default are preserved.\n']
for variant in ('eevdf', 'cfs'):
    release = '6.6.0-cis7000-' + variant
    entry = re.sub(r'^\s*linux\s+[^\n]+$',
                   lambda _: linux[0].group(1) + '/boot/vmlinuz-' + release + args, body, flags=re.M)
    entry = re.sub(r'^\s*initrd\s+[^\n]+$',
                   lambda _: initrd[0].group(1) + '/boot/initrd.img-' + release, entry, flags=re.M)
    output.append("menuentry 'CIS7000 " + variant + "' --id cis7000-" + variant + " {\n" + entry + '}\n')
pathlib.Path(destination).write_text(''.join(output))
PY
grub-script-check "$staging/custom.cfg"
# All validation above completes before changing installed files.
for variant in eevdf cfs; do
    tree="$project_root/work/linux-$variant"
    out="$project_root/work/build-$variant"
    release="6.6.0-cis7000-$variant"
    sudo -n make -C "$tree" O="$out" LOCALVERSION= INSTALL_MOD_STRIP=1 modules_install
    sudo -n install -m 0600 "$out/arch/x86/boot/bzImage" "/boot/vmlinuz-$release"
    sudo -n install -m 0600 "$out/System.map" "/boot/System.map-$release"
    sudo -n install -m 0644 "$out/.config" "/boot/config-$release"
    sudo -n mkinitramfs -o "/boot/initrd.img-$release" "$release"
    [[ -s "/boot/initrd.img-$release" ]]
    sudo -n sha256sum "/boot/vmlinuz-$release" "/boot/System.map-$release" \
        "/boot/config-$release" "/boot/initrd.img-$release" > "$staging/$variant.sha256"
done
sudo -n sha256sum -c "$staging/original.sha256"
sudo -n install -m 0644 "$staging/custom.cfg" /boot/grub/custom.cfg
sudo -n cmp "$staging/grub.cfg.original" /boot/grub/grub.cfg
sha256sum /boot/grub/custom.cfg > "$staging/custom.sha256"
printf 'Installed both kernels; original GRUB configuration unchanged. Records: %s\n' "$staging"
echo 'No boot selection or reboot was performed.'
