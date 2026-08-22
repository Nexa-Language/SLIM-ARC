# Reproducing Experiments

复现顺序：先固定代码和模型哈希，再固定设备、存储、缓存状态、内存/CPU 约束和负载，
最后运行 baseline 与 SLIM-ARC。不得把不同合同的结果拼成累计加速比。

1. 阅读 [结果索引](../results/README.md)，选择同一设备和实验批次。
2. 保存 `git rev-parse HEAD`、模型 SHA-256、`uname`、CPU、内存、存储挂载和 swap。
3. 明确 cold/warm cache；无法清缓存时必须标记。
4. 记录完整命令、环境变量、退出码、stdout/stderr 和 wall time。
5. 至少重复两次；报告中位数和区间，异常值不得静默删除。

基础脚本位于 `scripts/bench/`、`scripts/macos/` 和 `scripts/pi/`。部分 cgroup、page cache
或 swap 操作需要管理员权限，执行前应单独审阅。
