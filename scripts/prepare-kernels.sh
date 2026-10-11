#!/usr/bin/env bash
# Fetch matching scheduler sources without overwriting existing work.
# Run from any directory: bash /path/to/project/scripts/prepare-kernels.sh
set -euo pipefail

project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$project_root/configs/kernel-source.env"

checkouts=("$project_root/work/linux-eevdf" "$project_root/work/linux-cfs")
scheduler_paths=(
    /include/linux/sched.h
    /kernel/sched/core.c
    /kernel/sched/debug.c
    /kernel/sched/fair.c
    /kernel/sched/features.h
    /kernel/sched/sched.h
)

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

verify_revision() {
    local checkout=$1
    [[ $(git -C "$checkout" rev-parse HEAD) == "$LINUX_COMMIT" ]] ||
        fail "$checkout has a different revision; leaving it untouched."
    [[ $(git -C "$checkout" rev-parse "refs/tags/$LINUX_TAG^{commit}") == "$LINUX_COMMIT" ]] ||
        fail "$LINUX_TAG does not match the pinned commit."
}

verify_clean() {
    local status
    status=$(git -C "$1" status --porcelain --untracked-files=all) ||
        fail "Could not check local changes in $1."
    [[ -z "$status" ]] || fail "$1 has local changes; leaving it untouched."
}

# Check both existing destinations before changing anything.
for checkout in "${checkouts[@]}"; do
    if [[ -e "$checkout" || -L "$checkout" ]]; then
        [[ -d "$checkout/.git" ]] || fail "$checkout is not a standalone Git checkout."
        [[ $(git -C "$checkout" rev-parse --show-toplevel) == "$checkout" ]] ||
            fail "$checkout resolves to a different repository."
        [[ $(git -C "$checkout" remote get-url origin) == "$LINUX_REPOSITORY" ]] ||
            fail "$checkout has an unexpected origin."
        verify_revision "$checkout"
        verify_clean "$checkout"
        for path in "${scheduler_paths[@]}"; do
            [[ -f "$checkout$path" ]] || fail "$checkout is missing $path."
        done
    fi
done

author_name=$(git -C "$project_root" config user.name || true)
author_email=$(git -C "$project_root" config user.email || true)
[[ -n "$author_name" && -n "$author_email" ]] || fail "Configure your Git name and email first."
mkdir -p "$project_root/work"

for checkout in "${checkouts[@]}"; do
    if [[ ! -e "$checkout" ]]; then
        git clone --no-checkout --depth 1 --filter=blob:none \
            --branch "$LINUX_TAG" "$LINUX_REPOSITORY" "$checkout"
        verify_revision "$checkout"
        # Full Linux trees contain case-only filename differences. Set the
        # sparse paths before checkout so this also works on default macOS.
        printf '%s\n' "${scheduler_paths[@]}" |
            git -C "$checkout" sparse-checkout set --no-cone --stdin
        git -C "$checkout" checkout --detach "$LINUX_COMMIT"
        git -C "$checkout" config user.name "$author_name"
        git -C "$checkout" config user.email "$author_email"
        verify_clean "$checkout"
    fi
    printf 'Ready: %s (%s)\n' "$checkout" "$LINUX_COMMIT"
done
