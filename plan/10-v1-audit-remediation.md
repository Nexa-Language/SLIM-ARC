# 07-v1: 审计问题修复计划

## 时间
2026-06-23

## 背景
独立 agent 审计报告（[`plan/audit/00-v1-completion-audit.md`](audit/00-v1-completion-audit.md)）指出严重问题。必须诚实面对，逐一修复。

## 审计问题分类

### P0 必须立即修复（可信度问题）
1. **80B 数据无原始日志**: 声称的 80B 性能数字无法溯源到任何 `logs/` 文件
   - 修复: 重新跑 80B 测试，保存完整原始日志到 `logs/ablation/raw-80b/`
   - 若无法复现，公开承认

2. **CSV 数据矛盾与挑选**: 四份 CSV 数据波动大（58-98%），报告只挑有利一组
   - 修复: 报告中呈现全部四份 CSV 数据，说明测量噪声问题
   - 修复: 做多次测量取中位数，而非挑选

3. **baseline OOM 自相矛盾**: 三份报告对"baseline 能否跑 80B"说法不一致
   - 修复: 统一口径 — 禁用 repack 后 baseline 在 8GB 也能跑（不 OOM），只是慢
   - 删除"baseline OOM"的错误说法

4. **`scripts/env/setup-cgroups.sh` 不存在**: README 引用不存在的脚本
   - 修复: 创建 `scripts/env/setup-cgroups.sh`

### P1 应该修复（完成度真实性）
5. **Phase 2b KV 换页未集成**: 接口 only，标记为 ✅ 不准确
   - 修复: 降级标记为 ⚠️ 接口完成，集成未做
   - 或: 真正集成到推理流程（复杂度高）

6. **evict_layer 从未被调用**: 接口 only
   - 修复: 在 graph_compute 中集成 evict_layer 调用，或降级标记

7. **缺 phase2c 设计文档**
   - 修复: 创建 `docs/design/phase2c-dynamic-locking.md`

8. **无单点消融数据**
   - 修复: 补做"只关 MADV_RANDOM"和"只关 prefetch"的对比测试

### P2 可以做（锦上添花）
9. **Phase 3 "协同 > 单点"对比数据**
10. **Q8_0 精度对比**

## 执行步骤

### Step 1: 修复 80B 数据可信度（P0）
- 重新跑 80B 8GB baseline + slim-arc 测试
- 保存完整原始日志
- 若数据与之前声明不符，更新所有报告

### Step 2: 修复 CSV 矛盾与挑选（P0）
- 在消融报告中呈现全部四份 CSV 数据
- 说明测量噪声，改为"多次测量中位数"
- 删除挑选性引用

### Step 3: 统一 baseline OOM 口径（P0）
- 审查所有报告，删除"baseline OOM"的错误说法
- 明确：禁用 repack 后 baseline 在 8GB 能跑，只是慢；启用 repack 时 OOM

### Step 4: 创建 setup-cgroups.sh（P0）
- 把 `docs/guide/environment.md` 的命令脚本化

### Step 5: 修复模块完成度标记（P1）
- Phase 2b: ✅ → ⚠️ 接口完成，集成未做
- evict_layer: ✅ → ⚠️ 接口完成，未集成
- Phase 2d: ✅ → ⚠️ 隐式实现（内核 page cache），无独立代码

### Step 6: 补 phase2c 设计文档（P1）

### Step 7: 补单点消融（P1）
- 做只关 MADV_RANDOM、只关 prefetch 的对比

### Step 8: 补 Phase 3 协同对比数据（P2）

## 验收标准
- [ ] 80B 原始日志保存到 `logs/ablation/raw-80b/`
- [ ] 消融报告呈现全部 CSV 数据，无挑选
- [ ] 所有报告 baseline OOM 口径一致
- [ ] `scripts/env/setup-cgroups.sh` 存在且可运行
- [ ] 模块完成度标记真实（接口 vs 集成）
- [ ] phase2c 设计文档存在
- [ ] 至少一组单点消融数据
