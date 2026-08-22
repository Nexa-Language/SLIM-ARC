#!/usr/bin/env bash

set -euo pipefail

readonly repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly source_dir="$repo_root/docs/wiki"
readonly wiki_url="git@github.com:Nexa-Language/SLIM-ARC.wiki.git"
readonly work_root=$(mktemp -d "${TMPDIR:-/tmp}/slim-arc-wiki.XXXXXX")

cleanup() {
    case "$work_root" in
        "${TMPDIR:-/tmp}"/slim-arc-wiki.*) rm -rf -- "$work_root" ;;
        *) echo "Refusing to remove unexpected Wiki temp path: $work_root" >&2 ;;
    esac
}
trap cleanup EXIT

git clone "$wiki_url" "$work_root/wiki"
find "$work_root/wiki" -maxdepth 1 -type f -name '*.md' -delete
cp "$source_dir"/*.md "$work_root/wiki/"
git -C "$work_root/wiki" add --all
if git -C "$work_root/wiki" diff --cached --quiet; then
    echo "GitHub Wiki is already synchronized."
    exit 0
fi
git -C "$work_root/wiki" commit -m '[doc] Synchronize project Wiki'
git -C "$work_root/wiki" push origin master
