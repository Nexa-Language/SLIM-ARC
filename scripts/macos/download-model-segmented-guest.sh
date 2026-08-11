#!/usr/bin/env bash

compute_ranges() {
    local start="${1:?start is required}"
    local end_exclusive="${2:?exclusive end is required}"
    local requested_segments="${3:?segment count is required}"
    local remaining=$((end_exclusive - start))
    local active_segments
    local base
    local extra
    local cursor="${start}"
    local index
    local length

    if (( remaining <= 0 || requested_segments <= 0 )); then
        return 0
    fi
    active_segments="${requested_segments}"
    if (( active_segments > remaining )); then
        active_segments="${remaining}"
    fi
    base=$((remaining / active_segments))
    extra=$((remaining % active_segments))
    for ((index = 0; index < active_segments; index++)); do
        length="${base}"
        if (( index < extra )); then
            length=$((length + 1))
        fi
        printf '%s %s %s\n' "${index}" "${cursor}" "$((cursor + length - 1))"
        cursor=$((cursor + length))
    done
}

if [[ -n "${BASH_SOURCE[1]:-}" ]]; then
    return 0
fi

set -euo pipefail

url="${1:?download URL is required}"
expected_size="${2:?expected size is required}"
expected_sha256="${3:?expected SHA-256 is required}"
final_path="${4:?final path is required}"
segment_count="${5:?segment count is required}"
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
if [[ "${final_path}" != "${expected_path}" || ! "${segment_count}" =~ ^[0-9]+$ ]] || (( segment_count < 2 || segment_count > 16 )); then
    printf 'Refusing unexpected destination or segment count\n' >&2
    exit 2
fi

partial_path="${final_path}.partial"
metadata_path="${partial_path}.metadata"
segment_dir="${partial_path}.segments"
expected_metadata="URL=${url}
SIZE=${expected_size}
SHA256=${expected_sha256}"
if [[ ! -f "${partial_path}" || ! -f "${metadata_path}" || "$(cat "${metadata_path}")" != "${expected_metadata}" ]]; then
    printf 'Segmented mode requires a partial file with matching pinned metadata\n' >&2
    exit 1
fi
if [[ -e "${final_path}" ]]; then
    printf 'Refusing to overwrite an existing final model\n' >&2
    exit 1
fi

starting_size="$(stat -c '%s' "${partial_path}")"
if (( starting_size > expected_size )); then
    printf 'Partial model is larger than the expected file\n' >&2
    exit 1
fi
if (( starting_size == expected_size )); then
    actual_sha256="$(sha256sum "${partial_path}" | awk '{print $1}')"
    if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
        printf 'Complete partial model failed SHA-256 verification\n' >&2
        exit 1
    fi
    mv "${partial_path}" "${final_path}"
    rm -f "${metadata_path}"
    printf 'MODEL_STATE=segmented_already_complete\nACTUAL_SHA256=%s\n' "${actual_sha256}"
    exit 0
fi

install -d -m 0755 "${segment_dir}"
mapfile -t ranges < <(compute_ranges "${starting_size}" "${expected_size}" "${segment_count}")
largest_segment=0
for row in "${ranges[@]}"; do
    read -r _ range_start range_end <<<"${row}"
    range_length=$((range_end - range_start + 1))
    if (( range_length > largest_segment )); then
        largest_segment="${range_length}"
    fi
done
available_bytes="$(df -PB1 "$(dirname "${final_path}")" | awk 'NR == 2 {print $4}')"
remaining_bytes=$((expected_size - starting_size))
if (( available_bytes < remaining_bytes + largest_segment + 1000000000 )); then
    printf 'Insufficient disk for segmented merge reserve\n' >&2
    exit 1
fi

download_segment() {
    local index="${1:?index is required}"
    local range_start="${2:?range start is required}"
    local range_end="${3:?range end is required}"
    local range_length=$((range_end - range_start + 1))
    local segment_path
    local work_path
    local chunk_size=268435456
    local work_size
    local chunk_start
    local chunk_end
    local chunk_length
    local chunk_path
    local http_code
    local actual_length
    segment_path="${segment_dir}/segment-${index}-${range_start}-${range_end}"
    work_path="${segment_path}.work"
    if [[ -f "${segment_path}" && "$(stat -c '%s' "${segment_path}")" == "${range_length}" ]]; then
        return 0
    fi
    if [[ ! -e "${work_path}" ]]; then
        : >"${work_path}"
    fi
    work_size="$(stat -c '%s' "${work_path}")"
    if (( work_size > range_length )); then
        printf 'Segment %s work file exceeds its range\n' "${index}" >&2
        return 1
    fi
    chunk_path="${work_path}.chunk"
    while (( work_size < range_length )); do
        chunk_start=$((range_start + work_size))
        chunk_end=$((chunk_start + chunk_size - 1))
        if (( chunk_end > range_end )); then
            chunk_end="${range_end}"
        fi
        chunk_length=$((chunk_end - chunk_start + 1))
        if [[ -e "${chunk_path}" ]]; then
            rm -f "${chunk_path}"
        fi
        http_code="$(
            curl --fail --location --http1.1 --retry 5 --retry-all-errors --silent --show-error \
                --range "${chunk_start}-${chunk_end}" \
                --output "${chunk_path}" \
                --write-out '%{http_code}' \
                "${url}"
        )"
        actual_length="$(stat -c '%s' "${chunk_path}")"
        if [[ "${http_code}" != "206" || "${actual_length}" != "${chunk_length}" ]]; then
            printf 'Segment %s chunk failed HTTP 206 or size validation\n' "${index}" >&2
            return 1
        fi
        cat "${chunk_path}" >>"${work_path}"
        work_size=$((work_size + chunk_length))
        if [[ "$(stat -c '%s' "${work_path}")" != "${work_size}" ]]; then
            printf 'Segment %s work length mismatch\n' "${index}" >&2
            return 1
        fi
        rm -f "${chunk_path}"
    done
    mv "${work_path}" "${segment_path}"
}

pids=()
for row in "${ranges[@]}"; do
    read -r index range_start range_end <<<"${row}"
    download_segment "${index}" "${range_start}" "${range_end}" &
    pids+=("$!")
done
failed=0
for pid in "${pids[@]}"; do
    if ! wait "${pid}"; then
        failed=1
    fi
done
if (( failed != 0 )); then
    printf 'One or more model segments failed\n' >&2
    exit 1
fi

expected_current="${starting_size}"
for row in "${ranges[@]}"; do
    read -r index range_start range_end <<<"${row}"
    if (( range_start != expected_current )); then
        printf 'Segment ranges are not contiguous\n' >&2
        exit 1
    fi
    segment_path="${segment_dir}/segment-${index}-${range_start}-${range_end}"
    cat "${segment_path}" >>"${partial_path}"
    expected_current=$((range_end + 1))
    if [[ "$(stat -c '%s' "${partial_path}")" != "${expected_current}" ]]; then
        printf 'Partial length mismatch after segment %s\n' "${index}" >&2
        exit 1
    fi
    rm -f "${segment_path}"
done
rmdir "${segment_dir}"

actual_sha256="$(sha256sum "${partial_path}" | awk '{print $1}')"
if [[ "$(stat -c '%s' "${partial_path}")" != "${expected_size}" || "${actual_sha256}" != "${expected_sha256}" ]]; then
    printf 'Segmented model failed final size or SHA-256 verification\n' >&2
    exit 1
fi
mv "${partial_path}" "${final_path}"
rm -f "${metadata_path}"
printf 'MODEL_STATE=segmented_downloaded_and_verified\n'
printf 'ACTUAL_SHA256=%s\n' "${actual_sha256}"
