# 评测运行日志

> 每次跑完一轮评测都追加一段。记录：环境、参数、结果、耗时、踩到的坑、下一步。
> 目的：**任何一次分数都能追溯到当时的代码版本与参数**（可复现是评测的底线）。

---

## 运行 #001 · 2026-10-12 夜 · DeepSeek 首个基线

### 环境与参数

| 项 | 值 |
|---|---|
| 数据集 | `evaluation/datasets/ceval_benchmark100.csv`（100 题 / 7 科目） |
| 脚本 | `evaluation/scripts/eval_choice.py` · 模式 `deepseek` |
| 模型 | `deepseek-chat` |
| 采样参数 | `temperature=0.0`、`max_tokens=16`、`RETRY=3` |
| 运行机 | 家电脑（本机 venv：openai 3.22.1 / pandas 3.0.6） |
| 结果文件 | `evaluation/results/benchmark_deepseek.csv` |
| 累计调用耗时 | 63.2 秒（100 题串行；平均约 0.6 s/题） |

### 结果

**总体准确率：87.0%（87/100）｜parse_fail 0 题**

| 科目 | 正确 / 总数 | 准确率 |
|---|---|---|
| business_administration（工商管理） | 8 / 10 | 80.0% |
| tax_accountant（税务） | 21 / 26 | 80.8% |
| accountant（会计） | 23 / 28 | 82.1% |
| college_programming（编程，对照） | 7 / 8 | 87.5% |
| college_economics（经济） | 16 / 16 | 100% |
| law（法律） | 6 / 6 | 100% |
| logic（逻辑，对照） | 6 / 6 | 100% |

**错题 13 题**：
`accountant#27`、`accountant#30`、`accountant#32`、`accountant#43`、`accountant#44`、
`business_administration#9`、`business_administration#31`、`college_programming#35`、
`tax_accountant#30`、`tax_accountant#34`、`tax_accountant#41`、`tax_accountant#45`、`tax_accountant#47`

**初步观察**：三个财务类专业科目（工商 / 税务 / 会计）均在 80~82%，而通用科目（经济 / 法律 / 逻辑）满分。
→ 提示：模型的短板集中在**垂域专业知识**，与项目一的结论方向一致（领域概念错配）。

### 本轮踩到的坑（3 个，都是真 bug）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 断点续跑把大量题目"静默跳过"，说"已有 29 题"却只跑了 10 题 | 题库由 7 科目合并，**`id` 只在科目内唯一**（100 题只有 38 个不同 id）。用 `id` 单键去重 → `accountant#0` 跑过后 `law#0` / `logic#0` 被误判成已跑过 | 去重键改为 **`subject#id` 复合键** |
| 2 | 报表"总体准确率"只反映本轮新增的一小撮题 | 报表统计的是本轮 `rows`，而断点续跑会跳过已完成 → 只报最后 10 题 = 90%，虚高 | 报表改为**读取结果文件累计全量** |
| 3 | 错题清单打印 `id`，出现两个 `30` 无法分辨 | 同 #1，题号标识不唯一 | 清单一律打印 `subject#id` |

**核心教训（可复现性）**：**每道题必须有全局唯一标识**。数据集一旦由多个来源合并，单字段主键几乎必然冲突——
而这类 bug 的表现形式是"静静少跑一半题"，分数看着正常，最容易被忽略。

### 待改进（进 v2 清单）

- 未记录 `usage` token 数 → 无法核算真实成本。应在 `ask_model` 里把 `resp.usage` 一并落盘。
- 未记录脚本/数据集的版本指纹（可用文件 md5），跨天对比时难以确认"是不是同一套东西"。
- 单次运行无重复采样 → `temperature=0` 也存在非确定性，后续应每题采样 3 次统计通过率。

### 下一步

1. 接入第二个模型（Qwen），跑同一套 100 题 → **双模型对比表**
2. 从 13 道错题里挑 5 道做归因（错在哪：知识缺口 / 审题错 / 选项干扰 / 解析误判）
