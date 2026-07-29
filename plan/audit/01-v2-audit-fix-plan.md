# 审计修复计划

## 严重问题（必须修复）

### 1. tab:ablation_single Full 行数据拼接
- **现状**: pp64=4.44（core-iq4xs-32g.txt）+ tg48=3.77（ablation-full.txt），两个不同日志
- **修复**: 统一用 core-iq4xs-32g.txt 的数据 → pp64=4.44, tg48=3.03
- **影响**: 05_evaluation.tex tab:ablation_single + generate_figures_v2.py + generate_updated_figures.py

### 2. 32GB baseline=0.08 错误
- **现状**: fig_performance_landscape panel (a) 32GB baseline=0.08（与 8GB 相同，错误）
- **日志**: 80b-32g-baseline-pp64-tg48.txt 显示 pp64=5.89, tg48=3.01（这是 SLIM-ARC 无 FA，不是 upstream baseline）
- **修复**: 32GB baseline 改为 3.01（SLIM-ARC 无 FA），图注标注"SLIM-ARC 无 FlashAttention 作为 32GB 基线"
- **影响**: generate_figures_v2.py + 05_evaluation.tex 分析文字

### 3. fa-off 日志失败
- **现状**: 80b-32g-flashattn-off-pp64-tg48.txt 报错 "failed to create context"
- **修复**: 论文中标注"fa off 在 Qwen3-Next 上不支持，数据来自 SLIM-ARC 无 FA 配置"
- **影响**: 05_evaluation.tex tab:eval_flashattn

## 中等问题（建议修复）

### 4. fig_volatility caption 加"示意性数据"
### 5. fig_kv_and_threads 与 table 环境统一或标注差异
### 6. 小模型挑选标准说明
### 7. OLMoE 12GB 负结果文字说明
### 8. panel (d) pp=0.27→0.25
### 9. prefill 57%→66.7%
### 10. panel (c) 2.64 标注来源

## 图文一致性检查清单
- [ ] tab:ablation_single Full 行 = core-iq4xs-32g.txt (4.44/3.03)
- [ ] tab:ablation_single -MADV = no-madv.txt (3.72/2.15)
- [ ] tab:ablation_single -KVq4 = no-kvq4.txt (—/3.92)
- [ ] tab:ablation_single +Evict = evict.txt (—/3.30)
- [ ] tab:eval_flashattn = flashattn-auto/on/off 日志
- [ ] tab:eval_kv_quant Q4_0 = ablation-full 或 core-iq4xs-32g (4.44/3.03)
- [ ] fig_performance_landscape panel (a) 32GB baseline = 3.01（非 0.08）
- [ ] fig_performance_landscape panel (d) 8GB SLIM-ARC pp=0.25（非 0.27）
- [ ] fig_ablation_diverging Full = 3.03（非 3.77）
- [ ] fig_optimization_dumbbell 32GB Full = 3.03 或 5.16（热缓存）
