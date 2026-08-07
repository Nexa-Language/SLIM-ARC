# 2026-08-05 昨日实验归档

- 整理日期：2026-08-07
- 归档范围：2026-08-05 RK3588 SLIM-ARC 小模型实验（Qwen3-4B / OLMoE-1B-7B）全部产物
- 说明：昨日实验的报告、原始数据、环境快照、debug 日志已全部收纳至此文件夹，上级目录 `docs/rk3588_test_notes/` 不再保留散落文件

---

## 目录结构

```
2026-08-05-昨日实验归档/
├── README.md                        # 本说明文档
├── RK3588-SLIMARC测试报告-2026-08-05.md   # 昨日正式测试报告
├── root-cause-build-2026-08-05.md    # 编译失败根因分析
├── t6-finalize.txt                   # T6 收尾记录
├── 原始数据/                        # 昨日推理/下载原始输出（18 个）
│   ├── raw-smoke-*.txt              # 冒烟测试输出
│   ├── raw-bench-*.txt              # llama-bench 输出
│   ├── raw-infer-*.out/.stderr      # 冷/热缓存推理输出
│   ├── raw-olmoe.out / raw-nomadv.out / raw-kv-evict.out
│   └── download-qwen3-4b.log / download-olmoe.log   # 模型下载日志
├── 环境快照/                        # T0 环境预检快照（15 个）
│   ├── env-snapshot-rk3588.txt      # 环境快照
│   ├── storage-info.txt / network-check.txt / toolchain-check.txt
│   ├── cgroup-prep.txt / git-status-snapshot.txt
│   ├── binaries-check.txt / submodule-check.txt
│   ├── upstream-status.txt / src-status.txt / model-verify.txt
│   └── olmoe-*.txt                  # OLMoE 相关检查
└── debug日志/                       # 编译/补丁/临时测试日志（13 个）
    ├── apply-slim-arc-log*.txt      # 3 次打补丁日志
    ├── build-rk3588-attempt-*.log   # 3 次编译尝试日志
    ├── cmake-config-log.txt
    ├── test-cold-hot.sh/.log
    ├── test-nomadv-summary.txt / test-kv-evict-summary.txt
    └── hf-download-probe/test.txt
```

## 关联

- 本次 80B/长上下文测试归档：[`../80B-长上下文测试归档/README.md`](../80B-长上下文测试归档/README.md)
