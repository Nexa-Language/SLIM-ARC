# Logs Directory

This directory stores benchmark results, profiling outputs, and run logs.

## Structure

```
logs/
├── baseline-upstream-*.txt     # Upstream llama.cpp baseline results
├── comparison-*.txt            # Baseline vs SLIM-ARC comparison
├── prefetch-stats-*.txt        # Prefetch scheduler statistics
└── profile-*.txt               # Memory access profiling data
```

All `.log` and `.txt` files here are git-ignored. Results are timestamped.
