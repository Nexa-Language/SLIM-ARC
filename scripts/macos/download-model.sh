#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "${script_dir}/common.sh"

segments=1
if [[ "${1:-}" == "--segments" ]]; then
    segments="${2:-}"
    shift 2
fi
if [[ $# -ne 1 || ! "${segments}" =~ ^[0-9]+$ ]] || (( segments != 1 && segments != 8 )); then
    printf 'usage: download-model.sh [--segments 8] <result-dir>\n' >&2
    exit 2
fi
result_dir="$1"
assert_safe_result_dir "${result_dir}"
mkdir -p "${result_dir}"

require_command colima
require_command python3
require_command uv

profile="$(slim_arc_profile_name)"
metadata_path="$(mktemp /tmp/slim-arc-model-metadata.XXXXXX)"
manifest_temp="$(mktemp "${result_dir}/.model-manifest.XXXXXX")"

cleanup() {
    if [[ -n "${metadata_path:-}" && "${metadata_path}" == /tmp/slim-arc-model-metadata.* && -f "${metadata_path}" ]]; then
        rm -f "${metadata_path}"
    fi
    case "${manifest_temp:-}" in
        "${result_dir}"/.model-manifest.*)
            if [[ -f "${manifest_temp}" ]]; then
                rm -f "${manifest_temp}"
            fi
            ;;
    esac
}
trap cleanup EXIT

uv run python "${script_dir}/query_hf_model.py" >"${metadata_path}"
IFS=$'\t' read -r repo_id revision filename expected_size expected_sha256 < <(
    python3 - "${metadata_path}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    model = json.load(source)
print(model["repo_id"], model["revision"], model["filename"], model["size"], model["expected_sha256"], sep="\t")
PY
)

guest_path="/var/lib/slim-arc/models/${filename}"
download_url="https://huggingface.co/${repo_id}/resolve/${revision}/${filename}?download=true"
if (( segments == 1 )); then
    download_output="$(
        colima --profile "${profile}" ssh -- sudo bash -s -- \
            "${download_url}" "${expected_size}" "${expected_sha256}" "${guest_path}" \
            <"${script_dir}/download-model-guest.sh"
    )"
else
    download_output="$(
        colima --profile "${profile}" ssh -- sudo bash -s -- \
            "${download_url}" "${expected_size}" "${expected_sha256}" "${guest_path}" "${segments}" \
            <"${script_dir}/download-model-segmented-guest.sh"
    )"
fi
printf '%s\n' "${download_output}"
actual_sha256="$(printf '%s\n' "${download_output}" | tr -d '\r' | awk -F= '$1 == "ACTUAL_SHA256" {print $2}')"
if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
    printf 'Guest verification did not return the expected SHA-256\n' >&2
    exit 1
fi

python3 - "${metadata_path}" "${actual_sha256}" "${manifest_temp}" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

metadata_path, actual_sha256, output_path = sys.argv[1:]
with open(metadata_path, encoding="utf-8") as source:
    manifest = json.load(source)
manifest["actual_sha256"] = actual_sha256
manifest["verified_at"] = datetime.now(timezone.utc).isoformat()
with open(output_path, "w", encoding="utf-8") as output:
    json.dump(manifest, output, indent=2, sort_keys=True)
    output.write("\n")
PY
mv "${manifest_temp}" "${result_dir}/model-manifest.json"
printf 'MODEL_MANIFEST=%s\n' "${result_dir}/model-manifest.json"
