# Pi5（4GB）测试笔记目录索引

> 本目录存放 **Raspberry Pi 5 / 4GB RAM** 工作线的全部测试留痕（SLIM-ARC 三线并行中的 Pi5 线，
> 与 `docs/rk3588_test_notes/`、`docs/yituodabian_test_notes/` 严格隔离）。
> 2026-08-13 做过一次目录整理：散落在根目录的 08-04/08-05 历史文件已按日期归档，文件内容未做任何改动（仅移动与引用路径更新）。

## 目录结构

```
docs/pi5_4GB_test_notes/
├── README.md                          ← 本索引
├── 2026-08-05-修复与测试归档/          ← 08-04 ~ 08-05：环境搭建、补丁修复、Qwen3-4B 首轮测试
│   ├── Qwen3-4B-SLIMARC修复与测试报告-2026-08-05.md   （汇总报告）
│   ├── pi5_qwen3_4b_results.md                        （08-04 vanilla 基线结果）
│   ├── root-cause.md                                  （补丁编译失败根因分析）
│   ├── 任务Prompt-修复SLIMARC补丁.md                   （当时的任务文档 T0~T6）
│   ├── 原始数据/                                       （16 个 raw/smoke 输出，全部保留）
│   │   ├── smoke-slimarc.txt / smoke-slimarc-disabled.txt
│   │   ├── raw-41-basic-cold.txt / raw-41-basic-hot.txt
│   │   ├── raw-42-bench-p64n32.txt / raw-42-bench-p128n64.txt
│   │   ├── raw-43-kv-q4_0.txt
│   │   ├── raw-44-fa-auto.txt / raw-44-fa-off.txt
│   │   ├── raw-45-ctx512.txt / raw-45-ctx1024.txt
│   │   ├── raw-46-memory.txt / raw-46-time-v.txt
│   │   └── raw-47-kv-evict.txt / raw-47-no-madv.txt
│   └── 环境准备与文档/
│       ├── init_pi5.md                （4GB Pi 可行性分析与部署步骤）
│       └── pi5.md                     （全新设备安装清单）
└── 2026-08-13-rerun/                  ← 08-13：全矩阵重测 + 80B 探测
    ├── environment-snapshot.md        （环境快照：OS/内核/二进制版本/存储）
    ├── 重测报告-2026-08-13.md          （Qwen3-4B 重测汇总，含与 08-05 对比与诚实声明）
    ├── smoke-default.txt / smoke-disabled.txt
    ├── raw-51-basic-cold.txt / raw-51-basic-hot.txt
    ├── raw-52-bench-p64n32.txt / raw-52-bench-p128n64.txt
    ├── raw-53-kv-q4_0.txt
    ├── raw-54-fa-auto.txt / raw-54-fa-off.txt
    ├── raw-55-ctx512.txt / raw-55-ctx1024.txt
    ├── raw-56-memory.txt
    ├── raw-57-kv-evict.txt / raw-57-no-madv.txt
    └── 80b-probe/                     ← 80B MoE 在 4GB Pi5 上的探测（重大发现：可跑通）
        ├── 80B探测与改进分析报告.md     （10 组 probe 汇总 + 推荐配置）
        ├── 瓶颈分析-Pi5-80B.md         （0.1 t/s 瓶颈归因：A76 算力 + FUSE 缺页）
        ├── mmap-probe.py / mmap-probe-out.txt  （mmap/madvise 行为探测脚本与输出）
        ├── probe-00-env.txt           （环境探测：fuseblk/NTFS-3G/USB3）
        └── probe-01-* ~ probe-10-*    （每组含命令记录 -out.txt 与 RSS 采样 -rss.txt）
```

## 时间线索引

| 日期 | 归档目录 | 主题 | 关键结论 |
|------|----------|------|----------|
| 2026-08-04 | `2026-08-05-修复与测试归档/` | vanilla llama.cpp 基线 | Qwen3-4B 可跑（microSD 冷启动 ~0.3/0.4 t/s）；80B 判定不可行 |
| 2026-08-05 | `2026-08-05-修复与测试归档/` | SLIM-ARC 补丁修复 + 完整矩阵 | 5 次编译修复成功；bench tg32/tg64 = 3.48/2.93 t/s；KV_EVICT/NO_MADV 负面验证通过 |
| 2026-08-13 | `2026-08-13-rerun/` | Qwen3-4B 全矩阵重测 | bench pp64/tg32 = 12.38/4.60（upstream 升级带来的提升，非 SLIM-ARC，已在报告中声明） |
| 2026-08-13 | `2026-08-13-rerun/80b-probe/` | **80B MoE 探测** | **45GB 模型在 4GB Pi5 跑通**（RSS ~2.8GiB）；SLIM-ARC 默认比禁用快 ~13%（与 RK3588 相反）；CONF+BUDGET 门控最优（waste -80%，hit_rate 49.2%） |

## 命名约定

- `raw-NN-<项目>.txt`：llama-cli / llama-bench 原始输出（`script -qec ... --single-turn < /dev/null` 捕获）
- `smoke-*.txt`：冒烟测试输出
- `probe-NN-*.txt` / `probe-NN-out.txt` / `probe-NN-rss.txt`：80B 探测的命令记录 / 程序输出 / RSS 采样轨迹
- 编号 NN 仅表示时序，不代表重要性；raw-41~47 属 08-05 轮，raw-51~57 属 08-13 轮

## 数据真实性说明

1. 所有 raw 文件均为原始输出，**整理时只移动位置、未修改内容**。
2. 08-13 重测报告中已诚实声明两处口径差异：二进制从 b1-1c3c967 升级到 b106-70dfba5（bench 提升主要来自 upstream）；无 sudo 无法 drop_caches，"冷启动"实为页面缓存热状态。
3. probe-01 的 RSS 采样因抓错进程（timeout 包装器）失效，仅保留作跑通证据；probe-02 起已用 `pgrep -x llama-cli` 修正。
