# SLIM-ARC Test Suite

This directory contains integration tests for SLIM-ARC components.

## Test Categories

- `test_env.sh`: Verify cgroups v2 tiers are correctly configured
- `test_prefetch.cpp`: Unit tests for the prefetch scheduler
- `test_model_load.sh`: Verify Qwen3-4B loads correctly under upstream llama.cpp
- `test_bench_smoke.sh`: Quick smoke test of the benchmark pipeline

## Running Tests

```bash
# Environment tests
bash tests/test_env.sh

# Model loading smoke test
bash tests/test_model_load.sh data/models/Qwen3-4B-Q4_K_M.gguf

# Full benchmark comparison
bash scripts/bench/compare-baseline-vs-prefetch.sh low
```

## Test Results Location

Test and benchmark outputs are saved to `logs/`.
