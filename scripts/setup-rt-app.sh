#!/usr/bin/env bash
# Build the pinned rt-app locally under work/; no system-wide installation.
set -euo pipefail
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$project_root/configs/rt-app-source.env"
fail() { echo "Error: $*" >&2; exit 1; }
[[ $(uname -s) == Linux ]] || fail 'Run this on the Linux test node.'
jobs=${JOBS:-8}
[[ $jobs =~ ^[1-9][0-9]*$ ]] || fail 'JOBS must be positive.'
for command in git gcc make autoconf automake libtoolize pkg-config; do
    command -v "$command" >/dev/null || fail "Install $command; see benchmarks/rt-app/README.md."
done
pkg-config --exists json-c || fail 'Install libjson-c-dev first.'

tree="$project_root/work/rt-app"
out="$project_root/work/build-rt-app"
mkdir -p "$project_root/work"
if [[ ! -e "$tree" && ! -L "$tree" ]]; then
    # Keep history so upstream's git-describe version generation works.
    git clone --no-checkout "$RT_APP_REPOSITORY" "$tree"
    git -C "$tree" checkout --detach "$RT_APP_COMMIT"
fi
[[ -d "$tree/.git" && ! -L "$tree" ]] || fail "$tree is not a standalone checkout."
[[ $(git -C "$tree" rev-parse --show-toplevel) == "$tree" ]] || fail 'Unexpected checkout root.'
[[ $(git -C "$tree" remote get-url origin) == "$RT_APP_REPOSITORY" ]] || fail 'Unexpected rt-app origin.'
[[ $(git -C "$tree" rev-parse HEAD) == "$RT_APP_COMMIT" ]] || fail 'Unexpected rt-app revision.'
[[ -z $(git -C "$tree" status --porcelain --untracked-files=all) ]] || fail 'rt-app has local changes; leaving them untouched.'

cd "$tree"
if [[ ! -x configure ]]; then
    ./autogen.sh
fi
mkdir -p "$out"
cd "$out"
"$tree/configure"
make -j"$jobs"
test -x "$out/src/rt-app"
printf 'Built rt-app %s: %s\n' "$RT_APP_COMMIT" "$out/src/rt-app"
