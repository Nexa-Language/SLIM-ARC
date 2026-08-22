# Future Work

比赛后续研究围绕三个主线展开。

## 运行时与专家系统

- 将在线专家转移统计、跨层候选和 hot expert cache 统一到低开销预测路径，避免额外
  Router matmul 抵消 I/O overlap 收益。
- 研究按存储延迟、命中置信度和压力动态调整 Top-K 与逐层预算，并扩大跨 workload 重复。
- 将 expert reclaim 的页级安全边界扩展到更复杂的分片、分文件 GGUF 和远程存储。

## KV 与统一预算

- 完成 KV manager 到 `unified_io_scheduler` 的实际连接，使 Weight、Expert 和 KV 共享
  可验证的每 tick 字节预算，而不只共享接口。
- 为 sink/window、KV 量化和 mmap offload 建立同上下文长度、同精度的完整消融。

## 复现与论文

- 扩大 GSM8K/LongBench 等质量样本，明确 IQ2 requantization 与 eviction 的精度边界。
- 在原生 NVMe、eMMC、USB/FUSE 和 Apple Unified Memory 上重复同合同实验，报告区间而非
  最佳单点。
- 将结构化证据、图表生成和报告构建纳入可复现 artifact，准备系统方向论文投稿。

Edge Agent Harness 保留为低优先级系统展示：其研究问题是端侧模型的短上下文、低输出
速度和工具协议开销，不应取代 SLIM-ARC 内存运行时的核心评价。
