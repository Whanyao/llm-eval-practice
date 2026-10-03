# -*- coding: utf-8 -*-
r"""
rag_eval.py —— RAG 最小原型评测（实验 C）

为什么写这个脚本（一句话）：
    实验 B 证明了「让模型别乱说」的代价是「它也不敢说对的」。
    实验 C 换思路：不是让它闭嘴，而是**把资料递给它**——这就是 RAG。

RAG 三段式（本脚本就是这三段的极简实现）：
    ① 检索 retrieve  —— 从知识库找出最相关的 k 个文档片段
    ② 增强 augment   —— 把片段拼进 prompt（这一步没有模型参与，纯文本拼接）
    ③ 生成 generate  —— 模型只依据资料作答，资料没有就说不确定

知识库怎么来（诚实设计，很重要）：
    素材 = 评测集里「正常题 25 + 边界题 10」的标准答案 → 35 个片段
    **故意不入库**：冲突题、知识库外题的答案
    理由：那两类题的本质就是「知识库里没有的东西」。
         若把它们的答案也塞进库，模型直接抄到答案，实验就作弊了。

检索算法（故意用最笨的）：
    字符 2-gram 重叠率打分，取 top-k。
    不引入 embedding / 向量库 —— 初学阶段先用「能看懂的笨办法」跑通全流程，
    理解原理后换 embedding 只是替换 retrieve() 这一个函数。

用法：
    .\venv\Scripts\python.exe rag_eval.py              # RAG 模式，全量 45 题
    .\venv\Scripts\python.exe rag_eval.py 3            # 只跑前 3 题（冒烟）
    .\venv\Scripts\python.exe rag_eval.py nocontext    # 对照：有约束但不给资料（复现实验 B）
"""

import os
import sys
import time

import pandas as pd
from openai import OpenAI

# ============ 0. 配置区 ============
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]              # evaluation/ 目录
DATASETS = BASE / "datasets"
RESULTS = BASE / "results"
EVAL_SET = str(DATASETS / "finance_eval_v1.csv")        # 题目 + 标准答案（也是知识库素材）
JUDGE_SET = str(DATASETS / "finance_eval_v1.1.csv")     # 判分关键词用 v1.1（已修正）
RESULT_FILE = str(RESULTS / "eval_results_rag.csv")
KB_FILE = str(DATASETS / "kb_docs.md")                  # 知识库落盘，方便你打开看长什么样
MODEL = "deepseek-chat"
TEMPERATURE = 0.0
MAX_TOKENS = 400
TOP_K = 3                               # 检索取前几段
SLEEP = 0.3

# 只有这两层进知识库（理由见文件头注释）
KB_LAYERS = ["正常", "边界"]

SYS_WITH_CTX = (
    "你是一名企业资产管理系统的财务顾问。"
    "请严格依据用户提供的【参考资料】作答；"
    "如果参考资料中没有相关信息，请直接回答「我不确定」，不要编造。"
)
SYS_NO_CTX = (
    "你是一名企业资产管理系统的财务顾问，回答要准确、简洁。"
    "如果遇到你不确定或无法获知的信息，请直接回答「我不确定」，不要编造。"
)


def get_api_key():
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
        return winreg.QueryValueEx(k, "DEEPSEEK_API_KEY")[0]
    except Exception:
        return None


def judge(answer, keywords):
    """判分规则与 eval_v1.py 完全一致（保证两个脚本的分数可比）。"""
    if not answer:
        return None
    if "|" in keywords:
        return any(o.strip() in answer for o in keywords.split("|") if o.strip())
    if ";" in keywords:
        return all(r.strip() in answer for r in keywords.split(";") if r.strip())
    return keywords.strip() in answer


# ============ ① 检索 ============
def bigrams(s):
    """把字符串切成相邻两字的集合，如 '资产折旧' -> {'资产','产折','折旧'}。"""
    s = str(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def retrieve(question, docs, k=TOP_K):
    """
    最笨但可解释的检索：算问题与每段文档的 2-gram 重叠率，取最高的 k 段。
    返回 [(doc_id, score, text), ...]，按分数降序。
    """
    qb = bigrams(question)
    scored = []
    for doc_id, text in docs.items():
        db = bigrams(text)
        score = len(qb & db) / max(1, len(qb))
        scored.append((doc_id, score, text))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]


# ============ ② 增强（拼 prompt）============
def build_messages(question, hits, use_context):
    if not use_context:
        return [
            {"role": "system", "content": SYS_NO_CTX},
            {"role": "user", "content": question},
        ]
    blocks = "\n".join(f"[资料{i+1}｜{d[0]}]\n{d[2]}" for i, d in enumerate(hits))
    user = f"【参考资料】\n{blocks}\n\n【问题】\n{question}"
    return [
        {"role": "system", "content": SYS_WITH_CTX},
        {"role": "user", "content": user},
    ]


# ============ ③ 生成 ============
def ask_model(client, messages):
    try:
        resp = client.chat.completions.create(
            model=MODEL, messages=messages,
            temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    [调用失败] {e}")
        return None


def main():
    use_context = "nocontext" not in sys.argv
    limit = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    # 两种模式写不同结果文件，避免互相覆盖（10/3 nocontext 曾覆盖 RAG 明细的教训）
    result_file = str(RESULTS / ("eval_results_nocontext.csv" if not use_context else "eval_results_rag.csv"))

    api_key = get_api_key()
    if not api_key:
        sys.exit("✗ 没找到 DEEPSEEK_API_KEY")

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    qs = pd.read_csv(EVAL_SET, encoding="utf-8-sig")
    judges = pd.read_csv(JUDGE_SET, encoding="utf-8-sig").set_index("id")["judge_keywords"]
    if limit:
        qs = qs.head(limit)

    # ---- 建知识库：只取「正常 + 边界」层的标准答案 ----
    kb = {}
    for _, r in qs[qs["layer"].isin(KB_LAYERS)].iterrows():
        kb[f"id{int(r['id'])}"] = f"【{r['category']}】{r['question']}\n{r['golden_answer']}"

    with open(KB_FILE, "w", encoding="utf-8") as f:
        f.write(f"# 知识库（{len(kb)} 个片段，仅含正常题+边界题）\n\n")
        for k, v in kb.items():
            f.write(f"## {k}\n\n{v}\n\n")

    mode = f"RAG（注入 top-{TOP_K} 资料）" if use_context else "无资料对照（复现实验B）"
    print(f"模式：{mode}｜{len(qs)} 题｜知识库 {len(kb)} 段｜模型 {MODEL}｜t={TEMPERATURE}\n")

    rows = []
    for i, r in qs.iterrows():
        q, qid = r["question"], int(r["id"])
        # ① 检索
        hits = retrieve(q, kb) if use_context and kb else []
        # ② 增强
        messages = build_messages(q, hits, use_context and bool(kb))
        # ③ 生成
        answer = ask_model(client, messages)
        passed = judge(answer, str(judges.loc[qid]))

        # 归因用：本题的"真答案"是否被检索到（金标文档是否在 top-k 里）
        gold_doc = f"id{qid}"
        gold_rank = next((j + 1 for j, h in enumerate(hits) if h[0] == gold_doc), None)
        in_kb = gold_doc in kb

        rows.append({
            "id": qid, "category": r["category"], "layer": r["layer"],
            "question": q, "golden_answer": r["golden_answer"],
            "retrieved": ",".join(h[0] for h in hits),
            "gold_in_topk": (gold_rank is not None),
            "gold_rank": gold_rank,
            "gold_in_kb": in_kb,
            "model_answer": answer, "passed": passed,
        })
        mark = "√" if passed is True else ("×" if passed is False else "?")
        print(f"  [{i+1}/{len(qs)}] {mark} id={qid} 召回={','.join(h[0] for h in hits) or '-'}")

    res = pd.DataFrame(rows)
    res.to_csv(result_file, index=False, encoding="utf-8-sig")

    valid = res[res["passed"].notna()]
    print(f"\n明细已写入：{result_file}")
    print(f"\n========== 总体准确率 ==========")
    print(f"有效题数 {len(valid)} / 共 {len(res)}｜准确率 {valid['passed'].mean():.3f}")
    print("\n========== 分层准确率 ==========")
    print(valid.groupby("layer")["passed"].agg(["count", "sum", "mean"]).round(3).to_string())

    if use_context:
        print("\n========== 检索环节：金标文档命中率（只在库内的题上有意义）==========")
        inlib = valid[valid["gold_in_kb"]]
        print(f"知识库覆盖的题 {len(inlib)} 道｜金标进 top-{TOP_K} 的比例："
              f"{inlib['gold_in_topk'].mean():.1%}")

        print("\n========== 归因：失败到底怪检索还是怪生成 ==========")
        bad = valid[valid["passed"] == False]
        no_ret = bad[bad["gold_in_kb"] & ~bad["gold_in_topk"]]
        ret_but_wrong = bad[bad["gold_in_kb"] & bad["gold_in_topk"]]
        out_kb = bad[~bad["gold_in_kb"]]
        print(f"  A. 检索没召回（库里有但没捞到）: {len(no_ret)} 题 -> id {no_ret['id'].tolist()}")
        print(f"  B. 召回了但没答对（生成的责任）  : {len(ret_but_wrong)} 题 -> id {ret_but_wrong['id'].tolist()}")
        print(f"  C. 知识库里本来就没有（不该怪 RAG）: {len(out_kb)} 题 -> id {out_kb['id'].tolist()}")


if __name__ == "__main__":
    main()
