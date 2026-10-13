# -*- coding: utf-8 -*-
"""
项目二：C-Eval 100 题 —— 双模型对比表 v0

用法：
    python evaluation/scripts/compare_models.py

读入：
    results/benchmark_deepseek.csv   （DeepSeek 基线）
    results/benchmark_qwen.csv       （Qwen）

产出：
    控制台对比表
    reports/COMPARE_REPORT_v0.md     （可直接贴进简历/面试材料的表格）

统计口径：与 eval_choice.py 的 report() 完全一致 ——
    有效题 = passed 非空（PARSE_FAIL 的题不计入分母）
    准确率 = 有效题中 passed 为 True 的比例
两张表用同一把尺子量，这是双模型对比成立的前提（控制变量）。

对齐方式：用 subject#id 复合键逐题配对，而不是按行号 —— 两个模型
断点续跑的进度可能不同，按行号对齐会错位。
"""

import os
import pandas as pd

# ---------- 路径 ----------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # evaluation/
RESULTS = os.path.join(BASE, "results")
REPORTS = os.path.join(BASE, "reports")

MODELS = [
    ("DeepSeek", os.path.join(RESULTS, "benchmark_deepseek.csv"), "deepseek-chat"),
    ("Qwen", os.path.join(RESULTS, "benchmark_qwen.csv"), "Qwen/Qwen3-30B-A3B-Instruct-2507"),
]

OUT_MD = os.path.join(REPORTS, "COMPARE_REPORT_v0.md")
OUT_DIFF = os.path.join(RESULTS, "compare_disagreements.csv")


def load(path):
    """读取单个模型的结果文件，补一列 case_key（subject#id 复合键）。"""
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["case_key"] = df["subject"].astype(str) + "#" + df["id"].astype(str)
    df["passed"] = df["passed"].map({True: True, False: False})   # 空值保持 NaN
    return df


def stats(df):
    """按统一口径算总体指标。"""
    valid = df[df["passed"].notna()]
    return {
        "total": len(df),
        "valid": len(valid),
        "acc": valid["passed"].mean() if len(valid) else float("nan"),
        "parse_fail": int((df["parse_extract"] == "PARSE_FAIL").sum()),
    }


def main():
    frames = {}
    for name, path, model_id in MODELS:
        if not os.path.exists(path):
            print(f"[跳过] 找不到 {path}")
            continue
        frames[name] = load(path)

    if len(frames) < 2:
        print("需要两个模型的结果文件才能对比。")
        return

    ds, qw = frames["DeepSeek"], frames["Qwen"]
    sd, sq = stats(ds), stats(qw)

    # ---------- 1. 总体 ----------
    print("=" * 62)
    print("  项目二：C-Eval 100 题 · 双模型对比")
    print("=" * 62)
    print(f"{'模型':<12}{'有效/共':<14}{'准确率':<12}{'parse_fail':<12}")
    for name, s in (("DeepSeek", sd), ("Qwen", sq)):
        print(f"{name:<12}{s['valid']}/{s['total']:<11}{s['acc']:.3f}{'':<6}{s['parse_fail']:<12}")
    print(f"\n差值（Qwen − DeepSeek）: {(sq['acc'] - sd['acc']) * 100:+.1f} pp")

    # ---------- 2. 逐题对齐（只比对双方都跑过的题） ----------
    merged = ds.merge(qw, on="case_key", suffixes=("_ds", "_qw"))
    print(f"\n两模型共同答过的题: {len(merged)} / {len(ds)}")

    both_valid = merged[merged["passed_ds"].notna() & merged["passed_qw"].notna()]
    if len(both_valid):
        agree = (both_valid["passed_ds"] == both_valid["passed_qw"]).mean()
        print(f"同题样本上的一致率: {agree:.3f}（{int(round(agree * len(both_valid)))}/{len(both_valid)} 题结论相同）")

    # ---------- 3. 分科目 ----------
    by_ds = both_valid.groupby("subject_ds")["passed_ds"].agg(["count", "mean"])
    by_qw = both_valid.groupby("subject_qw")["passed_qw"].mean().rename("qwen_mean")
    sub = by_ds.join(by_qw)
    sub.columns = ["题数", "DeepSeek", "Qwen"]
    sub["差(pp)"] = (sub["Qwen"] - sub["DeepSeek"]) * 100
    sub = sub.sort_values("DeepSeek")
    for c in ("DeepSeek", "Qwen"):
        sub[c] = (sub[c] * 100).round(1)
    sub["差(pp)"] = sub["差(pp)"].round(1)

    print("\n---------- 分科目准确率 (%) ----------")
    print(sub.to_string())

    # ---------- 4. 分歧题（一错一对）----------
    dis = both_valid[both_valid["passed_ds"] != both_valid["passed_qw"]].copy()
    dis["谁对"] = dis.apply(lambda r: "Qwen" if r["passed_qw"] else "DeepSeek", axis=1)
    print(f"\n---------- 分歧题 {len(dis)} 道（一错一对，归因素材）----------")
    for _, r in dis.iterrows():
        print(f"  {r['case_key']:<18} 标准:{r['golden_ds']}  "
              f"DS:{r['parse_extract_ds']}  Qwen:{r['parse_extract_qw']}  → {r['谁对']} 对")

    if len(dis):
        cols = ["case_key", "subject_ds", "id_ds", "question_ds", "golden_ds",
                "model_raw_ds", "parse_extract_ds", "model_raw_qw", "parse_extract_qw", "谁对"]
        dis[cols].to_csv(OUT_DIFF, index=False, encoding="utf-8-sig")
        print(f"\n分歧题明细已写出: {os.path.relpath(OUT_DIFF, os.path.dirname(BASE))}")

    # ---------- 5. 报告 ----------
    os.makedirs(REPORTS, exist_ok=True)
    L = []
    L.append("# 项目二 · C-Eval 100 题 双模型对比 v0\n")
    L.append("## 一、总体\n")
    L.append("| 模型 | 有效题数 / 共 | 准确率 | parse_fail |")
    L.append("|---|---|---|---|")
    for name, model_id, s in (("DeepSeek", MODELS[0][2], sd), ("Qwen", MODELS[1][2], sq)):
        L.append(f"| {name}（`{model_id}`） | {s['valid']} / {s['total']} | **{s['acc']:.1%}** | {s['parse_fail']} |")
    L.append(f"\n差值（Qwen − DeepSeek）：**{(sq['acc'] - sd['acc']) * 100:+.1f} pp**\n")
    L.append("> 口径说明：有效题 = 成功提取出选项字母的题（`passed` 非空）；"
             "`parse_fail` 的题不计入分母。两模型使用同一题库、同一 prompt 模板、"
             "同一 temperature=0.0、同一 `MAX_TOKENS=16`、同一判分逻辑，仅模型不同。\n")

    L.append("## 二、分科目（同题样本对齐后）\n")
    L.append("| 科目 | 题数 | DeepSeek | Qwen | 差 |")
    L.append("|---|---|---|---|---|")
    for idx, r in sub.iterrows():
        L.append(f"| {idx} | {int(r['题数'])} | {r['DeepSeek']:.1f}% | {r['Qwen']:.1f}% | {r['差(pp)']:+.1f}pp |")

    L.append(f"\n## 三、分歧题（{len(dis)} 道）\n")
    if len(dis):
        L.append("| 题号 | 标准答案 | DeepSeek | Qwen | 谁答对 |")
        L.append("|---|---|---|---|---|")
        for _, r in dis.iterrows():
            L.append(f"| {r['case_key']} | {r['golden_ds']} | {r['parse_extract_ds']} | "
                     f"{r['parse_extract_qw']} | {r['谁对']} |")
        L.append("\n> 这 5 道（按需选取）是归因章节的核心素材：**一错一对**的题最能说明两个模型的差异在哪。\n")
    else:
        L.append("两模型结论完全一致，无分歧题。\n")

    L.append("## 四、结论（待补）\n")
    L.append("- 差异量级：\n- 偏科情况：\n- 典型失败模式：\n")

    with open(OUT_MD, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(L))
    print(f"\n对比报告已写出: {os.path.relpath(OUT_MD, os.path.dirname(BASE))}")


if __name__ == "__main__":
    main()
