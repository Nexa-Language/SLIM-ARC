# Data Directory

This directory holds models and benchmark datasets.

## Structure

```
data/
├── models/           # GGUF model files (git-ignored, downloaded)
│   ├── Qwen3-4B-Q4_K_M.gguf
│   └── Qwen3-Next-A3B-Q4_K_M.gguf (to be added)
├── hf-models/        # HuggingFace source models (git-ignored)
└── benchmarks/       # Benchmark datasets (git-ignored)
    ├── wikitext-103/
    ├── hellaswag/
    └── c4/
```

## Downloading Models

```bash
# Qwen3-4B (Dense, Q4_K_M)
huggingface-cli download Qwen/Qwen3-4B-GGUF Qwen3-4B-Q4_K_M.gguf --local-dir data/models

# Qwen3-Next-A3B (MoE) - to be added
```

## Benchmark Datasets

Use the scripts in `src/llama-upstream/scripts/` to download:

```bash
bash src/llama-upstream/scripts/get-wikitext-103.sh
bash src/llama-upstream/scripts/get-hellaswag.sh
```

All large files in this directory are git-ignored. Only this README is committed.
