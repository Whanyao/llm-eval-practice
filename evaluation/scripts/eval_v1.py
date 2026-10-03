# -*- coding: utf-8 -*-
r"""
eval_v1.py —— 财务评测集 v1 自动判分脚本（Step 3）

它做什么（一句话）：
    读题目 CSV → 逐题问 DeepSeek → 拿标准答案关键词判分 → 输出结果表 + 通过率报表

运行方式（一定要在项目目录下、用 venv 的 Python）：
    cd /d D:\Software\llm-eval-practice
    .\venv\Scripts\python.exe eval_v1.py

只跑前 3 题做冒烟测试：
    .\venv\Scripts\python.exe eval_v1.py 3

为什么这么设计（评测视角）：
    · temperature=0 —— 评测求可复现，固定参数测"能力基线"
    · 每道题一条独立 try-except —— 单题失败不能中断整轮（你压测的老思路）
    · 结果落盘 CSV —— 可追溯、可复算，这是"评测可复现"的底线
"""

import os
import sys
import json
import time

import pandas as pd
from openai import OpenAI


# ============ 0. 配置区（改这里就行） ============
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]              # evaluation/ 目录（脚本放 evaluation/scripts/ 下）
DATASETS = BASE / "datasets"                            # 评测集目录
RESULTS = BASE / "results"                              # 结果目录
EVAL_SET = str(DATASETS / "finance_eval_v1.csv")        # 评测集文件
RESULT_FILE = str(RESULTS / "eval_results_v1.csv")      # 结果明细落盘位置
MODEL = "deepseek-chat"                 # 被测模型
TEMPERATURE = 0.0                       # 评测固定 0，求可复现
MAX_TOKENS = 300                        # 财务题答案不长，300 够用
RETRY = 1                               # 失败重试次数
SLEEP = 0.3                             # 每次调用间隔（秒），避免打太快被限流


# ============ 1. 取 API Key（从环境变量读，绝不硬编码） ============
def get_api_key():
    """优先读环境变量；读不到时回退读 Windows 用户环境变量注册表（本地练习兜底）。"""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:  # 兜底：Windows 用户环境变量存在注册表里，某些终端不会自动继承
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        key, _ = winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")
        return key
    except Exception:
        return None


# ============ 2. 调用模型（带异常保护，对应你写的 safe_call） ============
def ask_model(client, question):
    """问一次模型，返回回答文本；失败返回 None（不抛异常，让主流程继续）。"""
    for attempt in range(RETRY + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    # system 固定角色：评测时所有题目用同一个 system，保证变量纯净
                    {"role": "system", "content": "你是一名企业资产管理系统的财务顾问，回答要准确、简洁。如果遇到你不确定或无法获知的信息，请直接回答「我不确定」，不要编造。"},
                    {"role": "user", "content": question},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if attempt < RETRY:
                time.sleep(1.5)
                continue
            print(f"    [调用失败] {e}")
            return None


# ============ 3. 判分（关键词规则） ============
def judge(answer, keywords):
    """
    判分规则（和评测集里的写法一一对应）：
      · 分号 ; 分隔 → 必须"全部出现"才算对（正常题/边界题）
      · 竖线 | 分隔 → 出现"任意一个"就算对（知识库外/冲突题）
      · 模型没答出（None）→ 返回 None，不计入准确率分母（但会记录）
    """
    if not answer:
        return None

    if "|" in keywords:
        options = [o.strip() for o in keywords.split("|") if o.strip()]
        return any(o in answer for o in options)

    if ";" in keywords:
        required = [r.strip() for r in keywords.split(";") if r.strip()]
        return all(r in answer for r in required)

    # 只有一个关键词的情况
    return keywords.strip() in answer


# ============ 4. 主流程 ============
def main():
    # 用法：python eval_v1.py [评测集文件名] [只跑前 N 题]
    #   例：python eval_v1.py                      -> 跑 v1 全量
    #       python eval_v1.py finance_eval_v1.1.csv -> 跑判分器 v1.1
    #       python eval_v1.py finance_eval_v1.1.csv 3 -> 跑前 3 题冒烟
    eval_set, limit = EVAL_SET, None
    for a in sys.argv[1:]:
        if a.isdigit():
            limit = int(a)
        else:
            # 允许只给文件名：自动到 datasets/ 目录找
            eval_set = a if Path(a).exists() else str(DATASETS / a)
    # 结果文件名跟着评测集走：finance_eval_X.csv -> eval_results_X.csv，统一落 results/（避免覆盖历史结果）
    result_file = str(RESULTS / Path(eval_set).name.replace("finance_eval", "eval_results"))

    api_key = get_api_key()
    if not api_key:
        print("✗ 没找到 API Key。请检查环境变量 DEEPSEEK_API_KEY 是否已设置。")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    df = pd.read_csv(eval_set)
    if limit:
        df = df.head(limit)
    print(f"评测集：{eval_set}｜共 {len(df)} 题｜模型：{MODEL}｜temperature={TEMPERATURE}\n")

    rows = []
    for i, r in df.iterrows():
        answer = ask_model(client, r["question"])
        passed = judge(answer, str(r["judge_keywords"]))
        rows.append({
            "id": r["id"],
            "category": r["category"],
            "layer": r["layer"],
            "question": r["question"],
            "golden_answer": r["golden_answer"],
            "model_answer": answer,
            "passed": passed,
        })
        # 实时打印进度：√ / × / ?（未取得回答）
        mark = "√" if passed is True else ("×" if passed is False else "?")
        print(f"  [{i+1}/{len(df)}] {mark}  id={r['id']}  {str(r['question'])[:32]}...")
        time.sleep(SLEEP)

    result = pd.DataFrame(rows)
    result.to_csv(result_file, index=False, encoding="utf-8-sig")
    print(f"\n明细已写入：{result_file}")

    # ---- 报表：总体 + 分层 + 分类（就是昨天 pandas 课的那两行） ----
    valid = result[result["passed"].notna()]
    print("\n========== 总体准确率 ==========")
    print(f"有效题数 {len(valid)} / 共 {len(result)}｜准确率 {valid['passed'].mean():.3f}")

    print("\n========== 分层准确率 ==========")
    print(valid.groupby("layer")["passed"].agg(["count", "sum", "mean"]).round(3).to_string())

    print("\n========== 分类准确率（找模型短板） ==========")
    by_cat = valid.groupby("category")["passed"].agg(["count", "sum", "mean"]).round(3)
    print(by_cat.sort_values("mean").to_string())

    # ---- badcase 清单：直接给 id，方便回头人工核查 ----
    bad = valid[valid["passed"] == False]
    print(f"\n========== badcase（{len(bad)} 题答错） ==========")
    print(", ".join(f"id{int(x)}" for x in bad["id"].tolist()) if len(bad) else "无")


if __name__ == "__main__":
    main()
