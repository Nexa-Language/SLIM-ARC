#!/usr/bin/env bash
set -euo pipefail

url="${1:?download URL is required}"
expected_size="${2:?expected size is required}"
expected_sha256="${3:?expected SHA-256 is required}"
final_path="${4:?final path is required}"
expected_filename="Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
expected_path="/var/lib/slim-arc/models/${expected_filename}"

url_prefix="https://huggingface.co/Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF/resolve/"
url_suffix="/${expected_filename}?download=true"
if [[ "${url}" != "${url_prefix}"*"${url_suffix}" ]]; then
    printf 'Refusing unexpected model URL\n' >&2
    exit 2
fi
url_revision="${url#"${url_prefix}"}"
url_revision="${url_revision%"${url_suffix}"}"
if [[ ! "${url_revision}" =~ ^[0-9a-f]{40}$ ]]; then
    printf 'Refusing invalid model URL revision\n' >&2
    exit 2
fi
if [[ ! "${expected_size}" =~ ^[0-9]+$ ]] || (( expected_size < 40000000000 || expected_size > 60000000000 )); then
    printf 'Refusing unexpected model size: %s\n' "${expected_size}" >&2
    exit 2
fi
if [[ ! "${expected_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
    printf 'Refusing invalid model SHA-256\n' >&2
    exit 2
fi
if [[ "${final_path}" != "${expected_path}" ]]; then
    printf 'Refusing unexpected model destination: %s\n' "${final_path}" >&2
    exit 2
fi

model_dir="$(dirname "${final_path}")"
partial_path="${final_path}.partial"
metadata_path="${partial_path}.metadata"
install -d -m 0755 "${model_dir}"

verify_file() {
    local candidate="${1:?candidate is required}"
    local actual_size
    local actual_sha256
    actual_size="$(stat -c '%s' "${candidate}")"
    [[ "${actual_size}" == "${expected_size}" ]] || return 1
    actual_sha256="$(sha256sum "${candidate}" | awk '{print $1}')"
    [[ "${actual_sha256}" == "${expected_sha256}" ]]
}

if [[ -e "${final_path}" ]]; then
    if verify_file "${final_path}"; then
        printf 'MODEL_STATE=already_verified\n'
        printf 'ACTUAL_SHA256=%s\n' "${expected_sha256}"
        exit 0
    fi
    printf 'Refusing to overwrite an existing model with mismatched size or hash\n' >&2
    exit 1
fi

expected_metadata="URL=${url}
SIZE=${expected_size}
SHA256=${expected_sha256}"
if [[ -e "${partial_path}" ]]; then
    if [[ ! -f "${metadata_path}" || "$(cat "${metadata_path}")" != "${expected_metadata}" ]]; then
        printf 'Partial model metadata does not match the pinned revision\n' >&2
        exit 1
    fi
else
    if [[ -e "${metadata_path}" ]]; then
        printf 'Refusing orphaned partial model metadata\n' >&2
        exit 1
    fi
    metadata_temp="${metadata_path}.tmp.$$"
    printf '%s\n' "${expected_metadata}" >"${metadata_temp}"
    mv "${metadata_temp}" "${metadata_path}"
fi

partial_size=0
if [[ -f "${partial_path}" ]]; then
    partial_size="$(stat -c '%s' "${partial_path}")"
fi
if (( partial_size > expected_size )); then
    printf 'Partial model is larger than the expected file\n' >&2
    exit 1
fi
available_bytes="$(df -PB1 "${model_dir}" | awk 'NR == 2 {print $4}')"
remaining_bytes=$((expected_size - partial_size))
if (( available_bytes < remaining_bytes + 1000000000 )); then
    printf 'Insufficient guest disk: need %s bytes plus reserve, have %s bytes\n' "${remaining_bytes}" "${available_bytes}" >&2
    exit 1
fi

curl --fail --location --retry 5 --retry-all-errors --continue-at - --silent --show-error --output "${partial_path}" "${url}"
if ! verify_file "${partial_path}"; then
    printf 'Downloaded model failed size or SHA-256 verification\n' >&2
    exit 1
fi
mv "${partial_path}" "${final_path}"
rm -f "${metadata_path}"
printf 'MODEL_STATE=downloaded_and_verified\n'
printf 'ACTUAL_SHA256=%s\n' "${expected_sha256}"
