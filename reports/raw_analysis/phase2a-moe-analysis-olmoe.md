
============================================================
MoE Expert Analysis: olmoe-1b-7b-0924-instruct-q4_k_m.gguf
============================================================

Architecture: olmoe
Total experts: 64
Experts used per token: 8
Sparsity: 87.5% (56/64 experts inactive)

--- Tensor Size Breakdown ---
Expert tensors:     3.63 GiB (48 tensors)
Non-expert tensors: 0.29 GiB (147 tensors)
Total:              3.92 GiB

--- Bandwidth Savings Analysis ---
Per-expert size (avg): 3.6 MiB

Full prefetch (all 64 experts):    3.63 GiB/forward
Predicted prefetch (top-8): 0.45 GiB/forward
Bandwidth reduction:           87.5%

--- Per-Layer Expert Size ---
 Layer |  Expert Size (MiB) |   Per Expert (MiB)
------ | ------------------ | ------------------
     0 |              249.0 |                3.9
     1 |              249.0 |                3.9
     2 |              216.0 |                3.4
     3 |              216.0 |                3.4
     4 |              249.0 |                3.9
  ... (16 layers total)

--- Prefetch Scheduling Implications ---
1. Expert prediction can reduce I/O by ~88%
2. With window=3, prefetch budget per layer: 87 MiB
3. Without prediction, prefetch budget: 698 MiB
4. Prediction accuracy of 80% saves ~70% bandwidth
