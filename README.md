# llm-eval-practice

大模型评测学习与实践仓库 —— 评测集构建 / 自动判分 / 模型对比 / RAG 评测 / 性能压测。

## 目录结构

```
llm-eval-practice/
├── evaluation/            # 评测项目区（本仓库主体，全部可展示产出）
│   ├── scripts/           # eval_v1.py / eval_choice.py / rag_eval.py / review_compare.py / arbitrate.py
│   ├── datasets/          # 评测集 finance_eval_v1(.1).csv、ceval_benchmark100.csv、RAG 知识库 kb_docs.md
│   ├── experiments/       # 控制变量实验（temperature 对照）
│   ├── results/           # 逐题明细、复核表（自动生成，可重跑再生）
│   └── reports/           # EVAL_REPORT_v1.md、ANNOTATION_GUIDELINE_v1.md、RUN_LOG.md
├── practice/              # 本地学习练习区（Day1-2 语法练习、API 首次调用等）
│                          # ⚠️ 已在 .gitignore 中，不推送 —— 仓库只放可展示产出
└── venv/                  # Python 虚拟环境（不入库）
```

## 项目一：财务·资产管理领域评测集 v1（已冻结 v1.0）

自建 45 题垂域评测集，对 `deepseek-chat` 完成一轮自动化评测 + 人工复核。

**核心结论**：原始准确率 46.7% → 人工复核校正后 55.6% → 剔除超纲题后有效准确率 **62.5%**。
模型的两大短板：**领域概念错配**（把资产对账答成银行对账、无形资产摊销规则错配）与**幻觉**（3/3 次对企业内部信息编造具体数值而非承认不知道）。

| 文件 | 说明 |
|---|---|
| [`EVAL_REPORT_v1.md`](evaluation/reports/EVAL_REPORT_v1.md) | **评测报告**：设计、结果、badcase 人工复核、短板定位、局限、实验 B/C 附录 |
| [`ANNOTATION_GUIDELINE_v1.md`](evaluation/reports/ANNOTATION_GUIDELINE_v1.md) | 标注规范 v1：双标注 Kappa 0.476 → 0.709 的过程记录 |
| `evaluation/datasets/finance_eval_v1.csv` | 评测集：45 题，分层设计（正常25/边界10/冲突5/知识库外5），含标准答案与判分关键词 |
| `evaluation/datasets/finance_eval_v1.1.csv` | 判分器 v1.1（只修关键词，题目冻结不动） |
| `evaluation/scripts/eval_v1.py` | 评测脚本：读题 → 批量调用 → 关键词判分 → 分层/分类准确率报表 |
| `evaluation/scripts/rag_eval.py` | RAG 最小原型：检索 → 拼 prompt → 生成（含 nocontext 对照模式） |
| `evaluation/scripts/review_compare.py` | 双标注一致性对比（Cohen's Kappa 手算实现） |
| `evaluation/scripts/arbitrate.py` | 仲裁脚本：按标注规范裁定分歧，产出定稿标签 |
| `evaluation/experiments/temp_experiment.py` | 控制变量实验：temperature 对输出稳定性的影响（t=0 三次完全一致 vs t=1.5 极差 8 tokens） |
| `evaluation/results/` | 逐题明细与复核表（可由脚本重新生成） |

### 评测集设计要点

- **分层设计**：正常题考知识、边界题考精度、冲突题考抗误导、知识库外题考幻觉 —— 与测试用例的"正常流/边界值/异常流"同构
- **可复现**：`temperature=0` 固定参数；评测集冻结后不再改动，保证任何改动的前后对比有效
- **判分规则**：正常/边界题关键词全含（`;`），知识库外/冲突题关键词任一（`|`）

## 项目二：C-Eval 中文基准 100 题批量评测

从公开中文基准 C-Eval val 集抽取 100 题（7 科目：会计 28 / 税务 26 / 经济 16 / 工商管理 10 / 编程 8 / 法律 6 / 逻辑 6），
自建选择题批量评测脚本，对 `deepseek-chat` 跑通自动判分基线。

**核心结论**：总体准确率 **87.0%**（87/100，`parse_fail` 0）。
分科目：**经济 / 法律 / 逻辑 100%**，编程 87.5%、会计 82.1%、税务 80.8%、工商管理 80.0%
—— **短板集中在三个财务专业科目，与项目一「领域概念错配」的结论同向**。

| 文件 | 说明 |
|---|---|
| `evaluation/datasets/ceval_benchmark100.csv` | 100 题 × 7 科目，含四个选项与标准答案 |
| `evaluation/scripts/eval_choice.py` | 选择题批量评测脚本：三模式（selftest / smoke / deepseek）、断点续跑、正则提取字母 |
| `evaluation/results/benchmark_deepseek.csv` | 逐题明细（含模型原始输出、提取结果、单题耗时） |
| [`RUN_LOG.md`](evaluation/reports/RUN_LOG.md) | 运行日志：环境 / 参数 / 结果 / **本轮抓到的 3 个真 bug** / v2 改进项 |

### 本轮抓到的 3 个真 bug（都是可复现性问题）

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 断点续跑"静默跳过"大量题目（说"已有 29 题"却只跑 10 题） | 题库由 7 科目合并，**`id` 只在科目内唯一**（100 题仅 38 个不同 id），单键去重导致 `accountant#0` 跑过后 `law#0` / `logic#0` 被误判为已跑过 | 去重键改 **`subject#id` 复合键** |
| 2 | 报表"总体准确率"虚高（只报最后 10 题 = 90%） | 报表只统计本轮新增行，而断点续跑会跳过已完成题 | 报表改为读结果文件**累计全量** |
| 3 | 错题清单出现两个 `30`，无法分辨 | 同 #1，题号标识不唯一 | 清单一律打印 `subject#id` |

> **核心教训**：多来源合并的数据集，**单字段主键几乎必然冲突**。
> 这类 bug 最阴险的地方是它**不报错**——表现为"静静少跑一半题"，分数看着正常，不逐题核对根本发现不了。

### 已知局限（v2 改进项）

- 关键词判分存在"同义不同词"与"正确但表述简洁"两类误杀（实测 4 题）→ 引入 **LLM-as-a-Judge**
- 单次采样未反映线上随机性 → 引入**双轨口径**（t=0 能力基线 + 线上参数多次采样通过率）
- 单模型，无法横向对比 → 增加第二厂商模型做对照

## 仓库约定（什么进仓库，什么留在本地）

| 内容 | 位置 | 是否推送 |
|---|---|---|
| 评测集、脚本、实验、报告、结果 | `evaluation/` | ✅ 推送（正式产出） |
| 语法练习、API 首次调用、随手脚本 | `practice/` | ❌ 本地保留，`.gitignore` 已排除 |
| 虚拟环境、缓存、密钥 | `venv/` / `*.pyc` / `.env` | ❌ 排除 |

判断标准：**这份文件是不是一份有方法论、有结论、可复现的正式产出？** 是则进仓库，只是"敲代码练手"的草稿就留本地。

## 复现方式

```powershell
cd D:\Software\llm-eval-practice

# 项目一：财务评测集 v1
.\venv\Scripts\python.exe evaluation\scripts\eval_v1.py        # 全量
.\venv\Scripts\python.exe evaluation\scripts\eval_v1.py 3      # 冒烟：只跑前 3 题
.\venv\Scripts\python.exe evaluation\scripts\rag_eval.py       # RAG 模式
.\venv\Scripts\python.exe evaluation\scripts\rag_eval.py nocontext    # 无资料对照

# 项目二：C-Eval 100 题（建议按 selftest -> smoke -> deepseek 顺序）
.\venv\Scripts\python.exe evaluation\scripts\eval_choice.py selftest   # 只测正则，不调 API、不花钱
.\venv\Scripts\python.exe evaluation\scripts\eval_choice.py smoke      # 单题冒烟，验证链路
.\venv\Scripts\python.exe evaluation\scripts\eval_choice.py deepseek   # 全量 100 题
```

依赖：Python 3.13 + `openai` + `pandas`；API Key 通过环境变量 `DEEPSEEK_API_KEY` 注入（不硬编码）。

## 学习轨迹

| 日期 | 内容 |
|---|---|
| Day 1 | LLM 核心概念：token / 注意力机制 / 训练三部曲 / 幻觉 / RAG / Agent / MCP；解码参数 temperature·top_p·top_k |
| Day 2 | Python 靶心（函数·异常·JSON·CSV·pandas）；首个 API 调用脚本；**temperature 对照实验**（t=0 三次输出完全一致 vs t=1.5 极差 8 tokens） |
| Day 3 | 垂域评测集构建 + 自动判分脚本 + 首份评测报告 + badcase 人工复核 |
| Day 4 | 标注规范 v1（双标注 Kappa 0.476 → 0.709）+ 拒答约束实验（净收益 −6.7pp）+ RAG 最小原型（44.4% → 93.3%） |
| Day 5 | 从零写选择题批量评测脚本（正则提取 / 断点续跑 / 分层报表）；C-Eval 100 题基线 **87.0%**；抓到 3 个可复现性 bug |
