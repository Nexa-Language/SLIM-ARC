
============================================================
MoE Expert Analysis: Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
============================================================

Architecture: qwen3next
Total experts: 512
Experts used per token: 10
Sparsity: 98.0% (502/512 experts inactive)

--- Tensor Size Breakdown ---
Expert tensors:     43.59 GiB (144 tensors)
Non-expert tensors: 1.49 GiB (663 tensors)
Total:              45.08 GiB

--- Bandwidth Savings Analysis ---
Per-expert size (avg): 1.8 MiB

Full prefetch (all 512 experts):    43.59 GiB/forward
Predicted prefetch (top-10): 0.85 GiB/forward
Bandwidth reduction:           98.0%

--- Per-Layer Expert Size ---
 Layer |  Expert Size (MiB) |   Per Expert (MiB)
------ | ------------------ | ------------------
     0 |              996.0 |                1.9
     1 |              996.0 |                1.9
     2 |              996.0 |                1.9
     3 |              996.0 |                1.9
     4 |              996.0 |                1.9
  ... (48 layers total)

--- Prefetch Scheduling Implications ---
1. Expert prediction can reduce I/O by ~98%
2. With window=3, prefetch budget per layer: 54 MiB
3. Without prediction, prefetch budget: 2790 MiB
4. Prediction accuracy of 80% saves ~78% bandwidth
