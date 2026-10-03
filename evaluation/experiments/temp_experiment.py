"""
Day 2 实验：温度对照实验（规范化版）
文件：evaluation\\experiments\\temp_experiment.py

【实验目的】
    验证 temperature 对输出稳定性的影响 —— 用数据说话，不用肉眼感觉。

【实验设计（控制变量法，评测的基本功）】
    固定不变的：问题、system 提示词、模型 —— 全程一个字都不改
    唯一变量：  temperature（0 和 1.5 两组）
    每组跑 3 次，记录每次的输出长度，看哪组稳定、哪组发散

【实验结论（2026-10-02 实测，结果见 temp_experiment.csv）】
    temperature=0：3 次输出完全一致（输出 tokens 与字数逐次相同）→ 可复现，适合评测基线
    temperature=1.5：3 次输出长度极差达 8 tokens，措辞发散 → 反映线上随机性
    推论：单次 t=0 结果只能测「能力基线」，要评估线上表现必须多次采样看通过率。

【为什么必须用脚本而不是手动截图】
    1. 变量锁死：脚本里 system 和 question 写死，不会手滑改错
    2. 自动记录：结果直接进表格，不用肉眼对比截图
    3. 可复现：明天想再验证一次，重跑一遍就行
    这三条就是"评测"和"随便玩玩"的区别。

运行方式：
    cd /d D:\\Software\\llm-eval-practice
    venv\\Scripts\\python.exe evaluation\\experiments\\temp_experiment.py
"""

import os
from pathlib import Path
import pandas as pd
from openai import OpenAI

# ------------------------------------------------------------
# 实验参数区：除了这里的 temperature，什么都不许动
# ------------------------------------------------------------
SYSTEM = "你是一个严谨的财务专家，回答简洁，控制在 50 字以内。"
QUESTION = "资产折旧常用的会计处理方法有哪些？"
MODEL = "deepseek-chat"
TEMPS = (0, 1.5)     # 两组对照
RUNS = 3             # 每组跑 3 次

client = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)

records = []
for temp in TEMPS:
    for run in range(1, RUNS + 1):
        print(f"正在跑 temperature={temp} 第 {run}/{RUNS} 次 ...")
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": QUESTION},
            ],
            temperature=temp,
        )
        answer = response.choices[0].message.content
        records.append({
            "温度": temp,
            "第几次": run,
            "输出tokens": response.usage.completion_tokens,
            "回答字数": len(answer),
            "回答前25字": answer[:25].replace("\n", " "),
        })

# ------------------------------------------------------------
# 用 pandas 出报表（今天上午学的六个操作，这里用到 4 个）
# ------------------------------------------------------------
df = pd.DataFrame(records)

print("\n========== 明细 ==========")
print(df.to_string(index=False))

print("\n========== 稳定性汇总 ==========")
summary = df.groupby("温度")["输出tokens"].agg(["min", "max"])
summary["极差(max-min)"] = summary["max"] - summary["min"]
print(summary)

print("\n========== 结论怎么读 ==========")
print("极差小 = 每次输出长度接近 = 稳定（t=0 应该是这样）")
print("极差大 = 每次输出长度飘忽 = 发散（t=1.5 应该是这样）")
print("这个『极差对比』就是你评测报告里的一张表。")

OUT_FILE = str(Path(__file__).resolve().parent / "temp_experiment.csv")   # 结果固定落在本脚本同目录
df.to_csv(OUT_FILE, index=False, encoding="utf-8-sig")
print(f"\n明细已保存：{OUT_FILE}")
