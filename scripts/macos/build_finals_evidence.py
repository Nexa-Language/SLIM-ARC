from __future__ import annotations

import argparse
import json
import math
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


GIB = 1024**3
ORDER = ("baseline", "patched-control", "patched-reclaim", "patched-residency", "patched-combined")
CACHES = ("cold", "warm")
TERMINAL_OUTCOMES = frozenset({"success", "oom", "timeout", "error"})
CAMPAIGN_OUTCOMES = TERMINAL_OUTCOMES | {"interrupted"}
COUNTERS = (
    "expert_samples", "expert_issued_bytes", "expert_hit_bytes", "expert_waste_bytes", "expert_advice_requests", "expert_coalesced_ranges", "expert_covered_bytes", "expert_advice_failures", "expert_invalid_ranges", "weight_requested_bytes", "weight_covered_bytes", "weight_issued_bytes", "weight_skipped_bytes", "weight_advice_requests", "weight_coalesced_ranges", "weight_invalid_ranges", "weight_advice_failures", "weight_rounds_throttled", "reclaim_candidates", "reclaim_calls", "reclaimed_bytes", "reclaim_skipped_bytes", "reclaim_failures", "residency_samples", "residency_admitted_experts", "residency_admitted_bytes", "residency_skipped_bytes", "residency_fallbacks", "pressure_normal", "pressure_high", "pressure_critical",
)
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RUN_KEY = re.compile(r"^runs/([a-z0-9-]+)$")
ENVS = {
    "baseline": ("baseline", {}),
    "patched-control": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1"}),
    "patched-reclaim": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1"}),
    "patched-residency": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}),
    "patched-combined": ("patched", {"SLIM_ARC_DECODE_MADV": "SEQUENTIAL", "SLIM_ARC_DYNAMIC_MADV": "1", "SLIM_ARC_EXPERT_RECLAIM_WASTE": "1", "SLIM_ARC_EXPERT_RESIDENCY": "1"}),
}
WORKLOAD_CONTRACT = {
    "seed": 1,
    "seed_source": "implicit_c_rand_default",
    "context_tokens": 80,
    "n_prompt": 64,
    "n_gen": 16,
    "n_depth": 0,
    "threads": 4,
    "no_warmup": True,
    "load_mode": "mmap",
    "offline": True,
}
BENCHMARK_CONTRACT = {key: value for key, value in WORKLOAD_CONTRACT.items() if key not in {"seed", "seed_source", "context_tokens"}}


@dataclass(frozen=True)
class Run:
    run_id: str
    source_directory: str
    round: int
    configuration: str
    cache_state: str
    outcome: str
    memory_peak_bytes: float | None
    major_faults: float | None
    read_blocks: float | None
    wall_seconds: float | None
    decode_tps: float | None
    expert_waste_bytes: float | None


def _obj(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _int(data: Mapping[str, object], key: str, minimum: int = 0) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _exact_int(value: object, expected: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value == expected


def _number(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{key} must be a finite non-negative number")
    return float(value)


def _regular(path: Path, name: str | None = None) -> Path:
    label = name or path.name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing or unsafe artifact: {label}")
    return path


def _directory(path: Path, name: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"unsafe directory: {name}")
    return path


def _load(path: Path) -> Mapping[str, object]:
    return _obj(json.loads(_regular(path).read_text(encoding="utf-8")), path.name)


def _sidecars(build_path: Path, campaign_path: Path) -> tuple[Mapping[str, object], Mapping[str, object]]:
    build, campaign = _load(build_path), _load(campaign_path)
    if build.get("schema_version") != 1 or campaign.get("schema_version") != 1:
        raise ValueError("unsupported sidecar schema")
    if not isinstance(build.get("git_commit"), str) or SHA1.fullmatch(build["git_commit"]) is None:
        raise ValueError("invalid build git_commit")
    for key in ("patched_source_sha256", "build_context_sha256", "model_sha256"):
        if not isinstance(build.get(key), str) or SHA256.fullmatch(build[key]) is None:
            raise ValueError(f"invalid build {key}")
    if build.get("llama_commit") != "360e134":
        raise ValueError("unpinned llama commit")
    images, linkage = _obj(build.get("image_ids"), "image_ids"), _obj(build.get("variant_linkage"), "variant_linkage")
    for variant in ("baseline", "patched"):
        image = images.get(variant)
        if not isinstance(image, str) or SHA256.fullmatch(image.removeprefix("sha256:")) is None or not image.startswith("sha256:"):
            raise ValueError("invalid image identity")
        if linkage.get(variant) != "verified":
            raise ValueError("pre-linkage evidence is invalid")
    if _int(campaign, "seed") != 1 or campaign.get("seed_source") != "implicit_c_rand_default":
        raise ValueError("campaign seed provenance mismatch")
    if _int(campaign, "context_tokens", 1) != 80:
        raise ValueError("campaign context mismatch")
    if _obj(campaign.get("benchmark_contract"), "benchmark contract") != BENCHMARK_CONTRACT:
        raise ValueError("benchmark contract mismatch")
    _obj(campaign.get("runs"), "campaign runs")
    return build, campaign


ELAPSED_PATTERN = re.compile(r"^(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)$")


def _elapsed_seconds(raw: str) -> float:
    matched = ELAPSED_PATTERN.fullmatch(raw)
    if matched is None:
        raise ValueError("invalid elapsed time")
    hours, minutes, seconds = matched.groups()
    seconds_value = float(seconds)
    if not math.isfinite(seconds_value) or seconds_value >= 60 or (hours is not None and int(minutes) >= 60):
        raise ValueError("invalid elapsed time")
    return (int(hours) * 3600 if hours is not None else 0) + int(minutes) * 60 + seconds_value


def _time(path: Path) -> tuple[float, int, int]:
    _regular(path)
    keys = ("Elapsed (wall clock) time (h:mm:ss or m:ss)", "Major (requiring I/O) page faults", "File system inputs")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        for key in keys:
            if line.strip().startswith(f"{key}: "):
                values[key] = line.strip().removeprefix(f"{key}: ")
    if len(values) != len(keys):
        raise ValueError("incomplete time artifact")
    try:
        faults, read_blocks = int(values[keys[1]]), int(values[keys[2]])
    except ValueError as error:
        raise ValueError("GNU time counters must be integers") from error
    if faults < 0 or read_blocks < 0:
        raise ValueError("GNU time counters must be non-negative")
    return _elapsed_seconds(values[keys[0]]), faults, read_blocks


def _decode(path: Path) -> float:
    _regular(path)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    values = [row.get("avg_ts") for row in rows if isinstance(row, dict) and row.get("n_prompt") == 0 and row.get("n_gen") == 16]
    if len(values) != 1 or isinstance(values[0], bool) or not isinstance(values[0], (int, float)) or not math.isfinite(values[0]) or values[0] < 0:
        raise ValueError("decode throughput must be a finite non-negative number")
    return float(values[0])


def _cgroup(path: Path, wrapper: Mapping[str, object]) -> None:
    _regular(path, "cgroup-after.txt")
    sections: dict[str, str] = {}
    current = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4]
        elif current and line.strip():
            sections[current] = line.strip()
    if sections.get("memory.max") != str(_int(wrapper, "memory_limit_bytes")) or sections.get("memory.swap.current") != "0" or sections.get("memory.swap.max") != "0":
        raise ValueError("cgroup no-swap evidence mismatch")
    cpu_fields = sections.get("cpu.max", "").split()
    if len(cpu_fields) != 2 or any(re.fullmatch(r"[0-9]+", field) is None for field in cpu_fields):
        raise ValueError("cgroup CPU evidence mismatch")
    quota, period = (int(field) for field in cpu_fields)
    if quota <= 0 or period <= 0 or quota != 4 * period:
        raise ValueError("cgroup CPU evidence mismatch")
    if quota != _int(wrapper, "cpu_quota", 1) or period != _int(wrapper, "cpu_period", 1):
        raise ValueError("cgroup CPU evidence mismatch")


def _campaign_labels(row: Mapping[str, object]) -> tuple[int, str, str, str]:
    round_number = _int(row, "round", 1)
    configuration, cache, outcome = row.get("configuration"), row.get("cache_state"), row.get("outcome")
    if configuration not in ENVS or cache not in CACHES or outcome not in CAMPAIGN_OUTCOMES:
        raise ValueError("invalid campaign finalist label or outcome")
    return round_number, configuration, cache, outcome


def _run_directory(root: Path, relative: str) -> Path:
    match = RUN_KEY.fullmatch(relative)
    if match is None or "\\" in relative or "//" in relative:
        raise ValueError("invalid campaign run path")
    _directory(root, "result root")
    runs = _directory(root / "runs", "runs")
    return _directory(runs / match.group(1), "campaign run")


def _controller_config(controller: Mapping[str, object], configuration: str, cache: str) -> tuple[str, Mapping[str, str]]:
    variant, environment = ENVS[configuration]
    config = _obj(controller.get("config"), "controller config")
    expected = {"memory_gib", "cpus", "pp", "tg", "repetitions", "timeout_seconds", "variant", "env"}
    if set(config) != expected or config.get("variant") != variant or config.get("env") != environment or _int(config, "memory_gib", 1) != 2 or _int(config, "cpus", 1) != 4 or _int(config, "pp", 1) != 64 or _int(config, "tg", 1) != 16 or _int(config, "repetitions", 1) != 1 or _int(config, "timeout_seconds", 1) < 30 or controller.get("cold_cache") != (cache == "cold"):
        raise ValueError("controller config does not match campaign")
    return variant, environment


def _oom_kill_event(controller: Mapping[str, object]) -> bool:
    events = controller.get("memory_events")
    if events is None:
        return False
    event_values = _obj(events, "controller memory_events")
    value = event_values.get("oom_kill", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("controller memory_events are invalid")
    return value > 0


def _validate_execution_state(controller: Mapping[str, object], outcome: str) -> None:
    return_code = controller.get("return_code")
    if return_code is not None and (isinstance(return_code, bool) or not isinstance(return_code, int)):
        raise ValueError("controller execution return code is invalid")
    timed_out = controller.get("timed_out")
    if not isinstance(timed_out, bool):
        raise ValueError("controller execution timeout state is invalid")
    state = _obj(controller.get("container_state"), "controller container_state")
    oom_killed = state.get("OOMKilled")
    if oom_killed is not None and not isinstance(oom_killed, bool):
        raise ValueError("controller execution OOM state is invalid")
    if outcome == "success":
        if not _exact_int(return_code, 0) or timed_out or not _exact_int(state.get("ExitCode"), 0) or oom_killed is not False:
            raise ValueError("successful controller has contradictory success execution state")
        return
    if outcome == "timeout":
        if not timed_out:
            raise ValueError("timeout controller has contradictory execution state")
        return
    if outcome == "oom":
        if timed_out or not (oom_killed is True or _oom_kill_event(controller)):
            raise ValueError("OOM controller has contradictory execution state")
        return
    if timed_out or oom_killed is True or return_code == 0:
        raise ValueError("error controller has contradictory execution state")


def _controller_identity(controller: Mapping[str, object], directory: Path, build: Mapping[str, object], configuration: str, cache: str) -> tuple[str, Mapping[str, str], str, Mapping[str, object] | None]:
    if controller.get("schema_version") != 1 or controller.get("run_id") != directory.name:
        raise ValueError("controller identity mismatch")
    variant, environment = _controller_config(controller, configuration, cache)
    if _int(controller, "memory_limit_bytes", 1) != 2 * GIB or _int(controller, "memory_swap_limit_bytes") != 0 or controller.get("llama_commit") != build["llama_commit"]:
        raise ValueError("controller resource or llama mismatch")
    image = _obj(build["image_ids"], "image_ids").get(variant)
    if controller.get("image_id") != image:
        raise ValueError("controller image identity mismatch")
    model = _obj(controller.get("model"), "controller model")
    if model.get("actual_sha256") != build["model_sha256"] or model.get("expected_sha256") != build["model_sha256"]:
        raise ValueError("model identity mismatch")
    outcome = controller.get("outcome")
    if outcome not in TERMINAL_OUTCOMES:
        raise ValueError("controller outcome is not terminal")
    _validate_execution_state(controller, outcome)
    contract = controller.get("workload_contract")
    if contract is not None and contract != WORKLOAD_CONTRACT:
        raise ValueError("controller workload contract mismatch")
    return variant, environment, outcome, contract if isinstance(contract, dict) else None


def _validate_campaign_binding(row: Mapping[str, object], outcome: str, image: object, contract: Mapping[str, object] | None) -> None:
    if row.get("outcome") != outcome:
        raise ValueError("campaign/controller outcome mismatch")
    if "image_id" in row and row["image_id"] != image:
        raise ValueError("campaign/controller image mismatch")
    if "workload_contract" in row and row["workload_contract"] != contract:
        raise ValueError("campaign/controller workload mismatch")


def _success_metrics(directory: Path, wrapper: Mapping[str, object], variant: str) -> tuple[float, int, int, float, float]:
    if _int(wrapper, "repetitions", 1) != 1:
        raise ValueError("finals protocol requires exactly one repetition")
    stdout = sorted(directory.glob("rep-*.stdout.log"))
    timing = sorted(directory.glob("rep-*.time.txt"))
    if [path.name for path in stdout] != ["rep-1.stdout.log"] or [path.name for path in timing] != ["rep-1.time.txt"]:
        raise ValueError("repetition artifact mismatch")
    metrics = wrapper.get("runtime_metrics")
    expected_status = "not_applicable" if variant == "baseline" else "collected"
    if wrapper.get("runtime_metrics_status") != expected_status:
        raise ValueError("invalid runtime metrics status")
    if not isinstance(metrics, list) or (variant == "baseline" and metrics) or (variant == "patched" and len(metrics) != 1):
        raise ValueError("runtime metrics repetition mismatch")
    waste = 0.0
    if metrics:
        metric = _obj(metrics[0], "runtime metric")
        if set(metric) != {"schema", *COUNTERS} or metric.get("schema") != 2:
            raise ValueError("invalid runtime metric schema")
        for name in COUNTERS:
            _int(metric, name)
        waste = float(_int(metric, "expert_waste_bytes"))
    wall, faults, reads = _time(timing[0])
    return wall, faults, reads, _decode(stdout[0]), waste


def _load_run(root: Path, relative: str, campaign_row: Mapping[str, object], build: Mapping[str, object]) -> Run:
    round_number, configuration, cache, campaign_outcome = _campaign_labels(campaign_row)
    directory = _run_directory(root, relative)
    controller_path = directory / "controller-result.json"
    if controller_path.is_symlink():
        raise ValueError("unsafe controller evidence artifact")
    if not controller_path.exists():
        if campaign_outcome != "interrupted":
            raise ValueError("terminal campaign row is missing controller evidence")
        return Run(directory.name, relative, round_number, configuration, cache, campaign_outcome, None, None, None, None, None, None)
    controller = _load(controller_path)
    variant, environment, outcome, controller_contract = _controller_identity(controller, directory, build, configuration, cache)
    _validate_campaign_binding(campaign_row, outcome, controller.get("image_id"), controller_contract)
    if outcome != "success":
        return Run(directory.name, relative, round_number, configuration, cache, outcome, None, None, None, None, None, None)
    if controller_contract != WORKLOAD_CONTRACT:
        raise ValueError("successful controller is missing workload contract")
    wrapper = _load(directory / "run-manifest.json")
    if wrapper.get("schema_version") != 1 or wrapper.get("outcome") != "success" or not _exact_int(wrapper.get("exit_code"), 0) or wrapper.get("variant") != variant or wrapper.get("environment") != environment or wrapper.get("image_id") != controller["image_id"] or _int(wrapper, "pp", 1) != 64 or _int(wrapper, "tg", 1) != 16 or _int(wrapper, "threads", 1) != 4 or _int(wrapper, "memory_limit_bytes", 1) != 2 * GIB or _int(wrapper, "memory_swap_limit_bytes") != 0 or wrapper.get("llama_commit") != build["llama_commit"] or wrapper.get("workload_contract") != WORKLOAD_CONTRACT:
        raise ValueError("wrapper contract mismatch")
    provenance = {"slim_arc_git_commit": "git_commit", "slim_arc_build_context_sha256": "build_context_sha256", "patched_source_sha256": "patched_source_sha256"}
    if any(wrapper.get(wrapper_key) != build[build_key] for wrapper_key, build_key in provenance.items()):
        raise ValueError("wrapper build provenance mismatch")
    _cgroup(directory / "cgroup-after.txt", wrapper)
    wall, faults, reads, decode, waste = _success_metrics(directory, wrapper, variant)
    return Run(directory.name, relative, round_number, configuration, cache, outcome, _number(wrapper, "memory_peak_bytes"), float(faults), float(reads), wall, decode, waste)


def _safe(row: Run, control: Run) -> bool:
    return row.wall_seconds <= 1.15 * control.wall_seconds and (row.major_faults == 0 if control.major_faults == 0 else row.major_faults <= 2 * control.major_faults) and (row.read_blocks == 0 if control.read_blocks == 0 else row.read_blocks <= 2 * control.read_blocks)


def _aggregate(values: Sequence[str]) -> str:
    return "insufficient_evidence" if "insufficient_evidence" in values else "promoted" if all(value == "promoted" for value in values) else "rejected" if "rejected" in values else "kept_opt_in"


def _beats_primary(candidate: Run, other: Run) -> bool:
    return candidate.memory_peak_bytes < other.memory_peak_bytes or candidate.expert_waste_bytes < other.expert_waste_bytes or candidate.read_blocks < other.read_blocks or candidate.decode_tps > other.decode_tps


def _median_run(rows: Sequence[Run]) -> Run:
    first = rows[0]
    return Run(f"median-{first.configuration}-{first.cache_state}", "", 0, first.configuration, first.cache_state, "success", statistics.median(row.memory_peak_bytes for row in rows), statistics.median(row.major_faults for row in rows), statistics.median(row.read_blocks for row in rows), statistics.median(row.wall_seconds for row in rows), statistics.median(row.decode_tps for row in rows), statistics.median(row.expert_waste_bytes for row in rows))


def _complete(runs: Sequence[Run]) -> bool:
    expected = {(configuration, cache) for configuration in ORDER for cache in CACHES}
    if {row.round for row in runs} != {1, 2} or len(runs) != 20 or any(row.outcome != "success" for row in runs):
        return False
    return all({(row.configuration, row.cache_state) for row in runs if row.round == round_number} == expected for round_number in (1, 2))


def build_finals_evidence(result_root: Path, build_evidence: Path, campaign_manifest: Path) -> dict[str, object]:
    build, campaign = _sidecars(build_evidence, campaign_manifest)
    campaign_runs = _obj(campaign["runs"], "campaign runs")
    if not campaign_runs:
        raise ValueError("campaign has no runs")
    resolved: set[Path] = set()
    runs: list[Run] = []
    for relative, row in sorted(campaign_runs.items()):
        if not isinstance(relative, str):
            raise ValueError("campaign run keys must be strings")
        directory = _run_directory(result_root, relative)
        real = directory.resolve(strict=True)
        if real in resolved:
            raise ValueError("duplicate real finalist evidence directory")
        resolved.add(real)
        runs.append(_load_run(result_root, relative, _obj(row, "campaign run"), build))
    groups = [(row.round, row.configuration, row.cache_state) for row in runs]
    if len(groups) != len(set(groups)):
        raise ValueError("duplicate finalist evidence")
    complete = _complete(runs)
    expected = {(configuration, cache) for configuration in ORDER for cache in CACHES}
    summaries = {(configuration, cache): _median_run([row for row in runs if row.configuration == configuration and row.cache_state == cache]) for configuration, cache in expected} if complete else {}
    aggregated_metrics = {f"{configuration}:{cache}": {"memory_peak_bytes": summaries[(configuration, cache)].memory_peak_bytes, "major_faults": summaries[(configuration, cache)].major_faults, "read_blocks": summaries[(configuration, cache)].read_blocks, "wall_seconds": summaries[(configuration, cache)].wall_seconds, "decode_tps": summaries[(configuration, cache)].decode_tps, "expert_waste_bytes": summaries[(configuration, cache)].expert_waste_bytes} for configuration, cache in sorted(expected)} if complete else {}
    per_cache: dict[str, dict[str, str]] = {}
    for cache in CACHES:
        if not complete:
            per_cache[cache] = {key: "insufficient_evidence" for key in ("reclaim", "residency", "combined")}
            continue
        rows = {configuration: summaries[(configuration, cache)] for configuration in ORDER}
        control, reclaim, residency, combined = rows["patched-control"], rows["patched-reclaim"], rows["patched-residency"], rows["patched-combined"]
        resident_good = (control.expert_waste_bytes > 0 and residency.expert_waste_bytes <= 0.9 * control.expert_waste_bytes) or (control.read_blocks > 0 and residency.read_blocks <= 0.9 * control.read_blocks) or (control.decode_tps > 0 and residency.decode_tps >= 1.1 * control.decode_tps)
        per_cache[cache] = {
            "reclaim": "rejected" if not _safe(reclaim, control) else "promoted" if reclaim.memory_peak_bytes <= 0.9 * control.memory_peak_bytes else "kept_opt_in",
            "residency": "rejected" if not _safe(residency, control) else "promoted" if resident_good else "kept_opt_in",
            "combined": "rejected" if not _safe(combined, control) else "promoted" if _beats_primary(combined, control) and (_beats_primary(combined, reclaim) or _beats_primary(combined, residency)) else "kept_opt_in",
        }
    return {"schema_version": 1, "runs": [asdict(row) for row in sorted(runs, key=lambda row: row.run_id)], "sample_counts": {f"{configuration}:{cache}": sum(row.configuration == configuration and row.cache_state == cache for row in runs) for configuration, cache in sorted(expected)}, "aggregated_metrics": aggregated_metrics, "per_cache": per_cache, "decisions": {key: _aggregate([per_cache[cache][key] for cache in CACHES]) for key in ("reclaim", "residency", "combined")}}


def write_finals_evidence(root: Path, result: Mapping[str, object]) -> None:
    _directory(root, "result root")
    outputs = (root / "finals-results.json", root / "finals-decision.md")
    if any(path.is_symlink() or (path.exists() and not path.is_file()) for path in outputs):
        raise ValueError("finals evidence output path is unsafe")
    outputs[0].write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decisions, per_cache = _obj(result.get("decisions"), "decisions"), _obj(result.get("per_cache"), "per_cache")
    lines = ["# SLIM-ARC finals promotion decision", "", "## Overall", *[f"- {key}: `{decisions[key]}`" for key in ("reclaim", "residency", "combined")], "", "## Cache-separated gates"]
    lines.extend(f"- {cache}: " + ", ".join(f"{key} `{_obj(per_cache[cache], cache)[key]}`" for key in ("reclaim", "residency", "combined")) for cache in CACHES)
    outputs[1].write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--build-evidence", required=True, type=Path)
    parser.add_argument("--campaign-manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        write_finals_evidence(args.result_root, build_finals_evidence(args.result_root, args.build_evidence, args.campaign_manifest))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Unable to build finals evidence: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
