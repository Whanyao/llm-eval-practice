# -*- coding: utf-8 -*-
r"""
eval_choice.py —— C-Eval 选择题批量评测脚本（评测项目②·第一晚）

它做什么（一句话）：
    读 100 题选择题 CSV → 逐题问模型（要求只输出字母）→ 正则提取字母 → 与答案比对 → 汇总分科目准确率

运行方式（在项目根目录、用 venv 的 Python）：
    cd /d D:\Software\llm-eval-practice
    .\venv\Scripts\python.exe evaluation\scripts\eval_choice.py selftest     ← 先跑这个（测你的正则）
    .\venv\Scripts\python.exe evaluation\scripts\eval_choice.py smoke        ← 单题冒烟（第 1 题）
    .\venv\Scripts\python.exe evaluation\scripts\eval_choice.py deepseek     ← 全量 100 题（第一晚目标）

========================= 今晚你要填的 4 个空（计划里叫步骤 2）=========================
    【TODO-1】build_prompt()   拼题面：题干 + 四个选项 + 「只输出字母」的硬性要求
    【TODO-2】extract_answer() 正则提取字母（资料：学习产出/Python正则速成-评测判分专用.md 第 148 行）
    【TODO-3】judge_one()      比对模型字母与标准答案
    【TODO-4】main() 的循环体   API 失败重试 3 次 + 逐题追加落盘（断点续跑）
填完先跑 selftest → smoke → 再跑 deepseek。卡住超过 15 分钟就喊我，我直接给参考实现。
====================================================================================
"""

import os
import re
import sys
import csv
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI


# ============ 0. 配置区（照搬 eval_v1.py 的路径写法，脚本从任何目录跑都不会错） ============
BASE = Path(__file__).resolve().parents[1]          # evaluation/
DATASETS = BASE / "datasets"
RESULTS = BASE / "results"

EVAL_SET = DATASETS / "ceval_benchmark100.csv"      # 100 题子集（7 科目，含 answer 列）

MODEL = "deepseek-chat"
TEMPERATURE = 0.0            # 评测固定 0：求可复现（这是"能力基线"，别动它）
MAX_TOKENS = 16              # ★关键：只让它吐一个字母，留 16 个 token 足够，废话少了提取成功率就高
RETRY = 3                    # API 失败重试次数
SLEEP = 0.4                  # 调用间隔，避免限流

# 每个模型一个结果文件：换模型只改 MODEL + 这个文件名
RESULT_FILE = RESULTS / "benchmark_deepseek.csv"


# ============ 1. 取 API Key（环境变量优先，注册表兜底；绝不硬编码） ============
def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        key, _ = winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")
        return key
    except Exception:
        return None


# ============ 2. 拼题面 ============
def build_prompt(row):
    """
    【TODO-1】把一行数据拼成发给模型的题面。要求：
      · 写清题干，四个选项各占一行（形如 "A. xxx"）
      · 最后加一句硬性格式要求：直接给出选项字母，不要解释
    为什么要"只输出字母"（面试可讲）：
      模型的解释越多，正则越容易抓错；约束输出格式 = 降低解析失败率，这是自动化判分的常规手法。
    返回：拼好的字符串
    """
    # 半成品：题头、题干、A 选项已经给你了。
    # 【你要做的】照着 A 那行的格式，把 B / C / D 三行补出来（只是换个列名）。
    return (
        "请回答以下单选题，只输出选项字母（A/B/C/D），不要输出任何解释。\n"
        "\n"
        f"{row['question']}\n"
        f"A. {row['A']}\n"
        # ↓↓↓ 在这里补 B / C / D 三行 ↓↓↓
        f"B. {row['B']}\n"
        f"C. {row['C']}\n"
        f"D. {row['D']}\n"

    )

# ============ 3. 从模型输出里提取选项字母 ============
def extract_answer(model_output):
    """
    【TODO-2】正则提取，返回 "A"/"B"/"C"/"D"，抓不到返回 "PARSE_FAIL"。
    资料：学习产出/Python正则速成-评测判分专用.md 第 148 行（有现成实现 + 6 条 assert 自测）
    思路提示：
      ① re.sub 把全角 ＡＢＣＤ 转成半角
      ② re.search 优先抓明确句式（答案/选/选项 + 字母），用 \b 词边界防止抓到题干里的字母
      ③ 兜底抓第一个独立字母
      ④ 都抓不到 → "PARSE_FAIL"（进人工兜底队列，绝不悄悄猜）
    为什么不能"猜"（面试可讲）：
      parse_fail 是数据质量问题，标出来人工处理；悄悄猜=把噪声混进准确率，评测结论就假了。
    """
    if not model_output:
        return "PARSE_FAIL"

    # ① 全角 ＡＢＣＤ → 半角 ABCD（全角字母的编码比半角大 0xFEE0）
    text = re.sub(r"[Ａ-Ｄａ-ｄ]", lambda m: chr(ord(m.group(0)) - 0xFEE0), model_output)

    # ② 先找"路标"（答案/选项/选），(?:...) 是路标不取，([A-D]) 才是要取的字母
    m = re.search(r"(?:答案|选项|选择|选)[为是：:\s]*([A-D])(?![A-Za-z])", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # ③ 兜底：抓"前后不挨着别的英文字母"的那个字母
    #    ⚠️ 这里不能用 \b！因为 Python 把中文也当"字"，"正确的是B" 里 B 前挨着"是"，
    #       \b 会认为还在一个词里而漏抓 → 改用前后否定环视 (?<![A-Za-z]) / (?![A-Za-z])
    m = re.search(r"(?<![A-Za-z])([A-D])(?![A-Za-z])", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # ④ 抓不到 → 进人工兜底队列，不悄悄猜
    return "PARSE_FAIL"


# ============ 4. 判分 ============
def judge_one(model_letter, golden_letter):
    """
    【TODO-3】选择题判分：字母相同即对。
    返回 True / False / None（None = 没提取到字母，不计入准确率分母）
    ⚠️ 和简答题的区别（面试可讲）：选择题是"精确匹配"（唯一正确答案），
       简答题是"关键词/语义匹配"。同一套框架支持两种题型 = 工程化能力。
    """
    # 第 1 步：没提取到字母（PARSE_FAIL）→ 返回 None，不进分母
    if model_letter == "PARSE_FAIL":
        return None
    # 第 2 步：两边都"去空格 + 转大写"再比，相等就是 True，不等就是 False
    return model_letter.strip().upper() == golden_letter.strip().upper()


# ============ 5. 调用模型（带重试） ============
def ask_model(client, prompt):
    """调一次模型；失败按 RETRY 次数重试，仍失败返回 None（不抛异常，避免单题中断整轮）。"""
    for attempt in range(RETRY + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "你是一个严谨的考试答题助手，只输出选项字母，不输出任何解释。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS,
            )
            return resp.choices[0].message.content
        except Exception as e:
            if attempt < RETRY:
                time.sleep(2)          # 退避 2 秒再试：网络抖动/限流的常规处理
                continue
            print(f"      [调用失败 {RETRY} 次] {e}")
            return None


# ============ 6. 汇总报表 ============
def report(df):
    valid = df[df["passed"].notna()]
    print("\n========== 总体准确率 ==========")
    print(f"有效题数 {len(valid)} / 共 {len(df)}｜准确率 {valid['passed'].mean():.3f}")

    print("\n========== 分科目准确率（看模型偏不偏科） ==========")
    by_sub = valid.groupby("subject")["passed"].agg(["count", "sum", "mean"]).round(3)
    print(by_sub.sort_values("mean").to_string())

    # ⚠️ 题号要用 subject#id 复合键，否则跨科目撞号时分不清是哪道题（例如两个 #30）
    def keys(sub):
        return [f"{s}#{i}" for s, i in zip(sub["subject"], sub["id"])]

    pf = df[df["parse_extract"] == "PARSE_FAIL"]
    print(f"\n========== parse_fail {len(pf)} 题（提取失败，需人工兜底） ==========")
    print(", ".join(keys(pf)) if len(pf) else "无")

    bad = valid[valid["passed"] == False]
    print(f"\n========== 错题 {len(bad)} 题（错题清单，后面要挑 5 道归因） ==========")
    print(", ".join(keys(bad)) if len(bad) else "无")


# ============ 7. 主流程 ============
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "smoke"

    # ---- 自测模式：先验证你的正则，再动真模型（红→绿：先看它失败，写完函数再看它通过）----
    if mode == "selftest":
        # ---- 第一部分：正则提取（TODO-2，已完成）----
        assert extract_answer("本题答案为 D，因为……") == "D"
        assert extract_answer("选 B") == "B"
        assert extract_answer("答案是Ｃ。") == "C"                    # 全角字母
        assert extract_answer("我认为答案是 d") == "D"                # 小写
        assert extract_answer("ABCD四个选项中，正确的是B。") == "B"      # 边界：不能抓成开头的 A
        assert extract_answer("抱歉，我无法回答。") == "PARSE_FAIL"     # 抓不到 → 不猜
        print("① extract_answer：6 条自测全部通过 ✅")

        # ---- 第二部分：拼题面（TODO-1，今晚这一步）----
        row0 = pd.read_csv(EVAL_SET).iloc[0]
        prompt0 = build_prompt(row0)
        print("\n【你的 build_prompt 拼出来的题面，长这样】")
        print("-" * 62)
        print(prompt0)
        print("-" * 62)

        miss = []
        if str(row0["question"])[:8] not in prompt0:
            miss.append("题干")
        for opt in "ABCD":
            if f"{opt}." not in prompt0:
                miss.append(f"{opt} 选项的「{opt}. 」标记")
            elif str(row0[opt])[:6] not in prompt0:
                miss.append(f"{opt} 选项的内容")
        if ("只" not in prompt0) and ("仅" not in prompt0):
            miss.append("「只输出字母」的格式要求")
        assert not miss, "题面里缺少：" + "、".join(miss)

        print("\n② build_prompt：验收通过 ✅（题干 / 四个选项 / 格式要求 三项齐全）")
        print("   下一步就可以跑 smoke 接真模型了")
        return

    api_key = get_api_key()
    if not api_key:
        print("✗ 没找到 API Key（环境变量 DEEPSEEK_API_KEY）")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    df = pd.read_csv(EVAL_SET)                 # 已是 UTF-8-sig；若你手动用 Excel 存过，会变 GBK，届时加 encoding='gbk'
    if mode == "smoke":
        df = df.head(1)
    print(f"题库：{EVAL_SET.name}｜{len(df)} 题｜模型：{MODEL}｜temperature={TEMPERATURE}\n")

    # ⚠️ 【踩坑记录】断点续跑的键必须是"全局唯一"的：
    #    题库由 7 个科目合并而来，id 只在科目内唯一 —— 100 题里只有 38 个不同 id！
    #    若只用 id 做键，accountant#0 跑过后，law#0 / logic#0 会被误判成"已跑过"而静默跳过。
    #    正确做法：用 subject#id 复合键（这也正是打印进度时用的那个标识）。
    def case_key(r):
        return f"{r['subject']}#{r['id']}"

    done_keys = set()
    if RESULT_FILE.exists() and mode != "smoke":
        prev = pd.read_csv(RESULT_FILE, encoding="utf-8-sig")
        done_keys = set(prev["subject"].astype(str) + "#" + prev["id"].astype(str))
        if done_keys:
            print(f"[断点续跑] 已有 {len(done_keys)} 题结果，自动跳过\n")

    first_write = not RESULT_FILE.exists()
    fields = ["subject", "id", "question", "golden", "model_raw", "parse_extract", "passed", "cost_s"]

    # ================= 【TODO-4】主循环 =================
    rows = []
    total = len(df)
    for i, (_, r) in enumerate(df.iterrows(), 1):
        rid = case_key(r)                       # 复合键：subject#id

        # ① 断点续跑：这题之前跑过就跳过
        if rid in done_keys:
            continue

        t0 = time.time()                        # 开始计时

        # ② ★★★ 评测流水线：四个函数接力，这一步你来写 ★★★
        #    第 1 步 拼题面    → build_prompt(r)
        #    第 2 步 问模型    → ask_model(client, 题面)
        #    第 3 步 提取字母  → extract_answer(模型原话)
        #    第 4 步 判对错    → judge_one(提取到的字母, r["answer"])
        #    四个函数都已写好，你只要【按顺序调用】+【把上一步的结果喂给下一步】。
        #    变量名建议：prompt / raw / letter / passed
        prompt = build_prompt(r)                    # ① 这一行数据 → 拼成题面
        raw = ask_model(client, prompt)             # ② 把题面发给模型，拿回原话
        letter = extract_answer(raw)                # ③ 从原话里正则提取出字母
        passed = judge_one(letter, r["answer"])     # ④ 和标准答案比对 → True/False/None

        cost = round(time.time() - t0, 2)

        row = {
            "subject": r["subject"], "id": r["id"], "question": r["question"],
            "golden": r["answer"], "model_raw": raw, "parse_extract": letter,
            "passed": passed, "cost_s": cost,
        }
        rows.append(row)

        # ③ 逐题追加落盘：答完一题立刻写一行 → 中途断了下次接着跑
        with open(RESULT_FILE, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if first_write:
                w.writeheader()
                first_write = False
            w.writerow(row)

        # ④ 进度：√ 答对 / × 答错 / ? 没提取到字母（进人工兜底）
        flag = "√" if passed else ("?" if passed is None else "×")
        print(f"[{i}/{total}] {flag}  {rid}  ({cost}s)")

    print(f"\n本轮新增 {len(rows)} 题｜明细文件：{RESULT_FILE.name}")

    # ⚠️ 【踩坑记录】报表必须统计【累计全量】，不能只用本轮新增的 rows：
    #    断点续跑会"跳过已完成"，只报本轮 = 只报最后那一小撮题的分数，看着漂亮、实则骗人。
    if RESULT_FILE.exists():
        allres = pd.read_csv(RESULT_FILE, encoding="utf-8-sig")
    else:
        allres = pd.DataFrame(rows)
    print(f"（下表统计累计全量 {len(allres)} 题，含此前已跑结果）")
    report(allres)


if __name__ == "__main__":
    main()
