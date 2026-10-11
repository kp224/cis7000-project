#!/usr/bin/env bash
# Replay the ordered CFS patch series onto an untouched, pinned Linux checkout.
# Usage: bash scripts/apply-cfs-patches.sh [checkout]
set -euo pipefail

fail() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

[[ $# -le 1 ]] || fail "Usage: $0 [checkout]"
project_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
source "$project_root/configs/kernel-source.env"
checkout=${1:-"$project_root/work/linux-cfs"}
patch_dir="$project_root/patches/cfs-6.6"

[[ -d "$checkout" ]] || fail "$checkout does not exist; run prepare-kernels.sh first."
checkout=$(cd "$checkout" && pwd -P)
# A .git entry plus the root comparison prevents Git walking up to our project.
[[ -d "$checkout/.git" || -f "$checkout/.git" ]] ||
    fail "$checkout is not a Git checkout."
repo_root=$(git -C "$checkout" rev-parse --show-toplevel) ||
    fail "Could not identify the checkout root."
[[ "$repo_root" == "$checkout" ]] || fail "Target resolves to a different repository."
origin=$(git -C "$checkout" remote get-url origin) || fail "Could not read origin."
[[ "$origin" == "$LINUX_REPOSITORY" ]] || fail "Target has an unexpected origin."
head=$(git -C "$checkout" rev-parse HEAD) || fail "Could not read HEAD."
[[ "$head" == "$LINUX_COMMIT" ]] ||
    fail "HEAD is not the pinned base (patches may already be applied); leaving it untouched."
git_dir=$(git -C "$checkout" rev-parse --absolute-git-dir) ||
    fail "Could not identify Git state."
for state in rebase-apply rebase-merge MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD sequencer; do
    [[ ! -e "$git_dir/$state" ]] ||
        fail "Unfinished Git operation ($state); resolve it before applying patches."
done
status=$(git -C "$checkout" status --porcelain --untracked-files=all) ||
    fail "Could not check local changes."
[[ -z "$status" ]] || fail "Target has local changes; leaving it untouched."

committer_name=$(git -C "$checkout" config user.name) || fail "Configure Git user.name first."
committer_email=$(git -C "$checkout" config user.email) || fail "Configure Git user.email first."
[[ -n "$committer_name" && -n "$committer_email" ]] || fail "Git identity must not be empty."

[[ -d "$patch_dir" && ! -L "$patch_dir" ]] || fail "Missing or unsafe patch directory."
[[ -f "$patch_dir/series" && -r "$patch_dir/series" && ! -L "$patch_dir/series" ]] ||
    fail "Missing, unreadable, or unsafe series manifest."
patches=()
while IFS= read -r filename || [[ -n "$filename" ]]; do
    # Only plain filenames: no options, traversal, directories, or shell syntax.
    [[ "$filename" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*\.patch$ ]] ||
        fail "Invalid patch filename in series: $filename"
    patch="$patch_dir/$filename"
    [[ -f "$patch" && -r "$patch" && ! -L "$patch" ]] ||
        fail "Missing, unreadable, or unsafe patch: $filename"
    # Reject duplicates before git am can partially apply a malformed manifest.
    for previous in "${patches[@]+"${patches[@]}"}"; do
        [[ "$previous" != "$patch" ]] || fail "Duplicate patch in series: $filename"
    done
    patches+=("$patch")
done < "$patch_dir/series"
[[ ${#patches[@]} -gt 0 ]] || fail "The patch series is empty."

# git am preserves each format-patch author; explicitly use the configured
# committer even when a caller has exported a different committer identity.
if ! GIT_COMMITTER_NAME="$committer_name" GIT_COMMITTER_EMAIL="$committer_email" \
    git -C "$checkout" am -- "${patches[@]}"; then
    fail "git am stopped; work and patch state are preserved in $checkout. Inspect and resolve it there."
fi
printf 'Applied %s patches to %s\n' "${#patches[@]}" "$checkout"
