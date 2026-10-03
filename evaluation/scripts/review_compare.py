# -*- coding: utf-8 -*-
r"""
review_compare.py —— 双标注一致性对比（AI 复核 vs 人工复核）

用途：把 eval_results_v1_reviewed.csv 里的两个复核列归一化到 4 个类别，
      算一致率 + Cohen's Kappa，并列出所有分歧条目。

为什么要有这个脚本：
  一个人标的（哪怕很认真）也可能标错/不一致。评测岗的标准做法是
  「背靠背双人标注 -> 算一致性 -> 分歧仲裁 -> 抽检校准」。
  这一步就是那个流程的最小可运行版本。

运行：
  .\venv\Scripts\python.exe review_compare.py
"""

import sys
from pathlib import Path
import pandas as pd

FILE = str(Path(__file__).resolve().parents[1] / "results" / "eval_results_v1_reviewed.csv")


def read_any_encoding(path):
    """Excel 一存，编码就从 utf-8 变成 gbk —— 这里两种都试一遍。"""
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"[读取成功] 编码 = {enc}")
            return df
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise SystemExit("两种编码都读不了，把文件发我看一眼")


def normalize(text):
    """把自由文本的复核意见归一化成 4 个标准类别。顺序即优先级。"""
    if not isinstance(text, str) or not text.strip():
        return None
    t = text.strip()
    if "超纲" in t:
        return "超纲"
    if "幻觉" in t or "瞎编" in t:
        return "幻觉"
    if "误杀" in t:
        return "误杀"
    if "真错" in t or "错" in t:
        return "真错"
    return "未识别"


def cohens_kappa(a, b):
    """手算 Cohen's Kappa，不依赖 sklearn。
    Po = 实际一致率；Pe = 随机一致率（按各自类别分布相乘求和）。
    Kappa = (Po - Pe) / (1 - Pe)
    """
    labels = sorted(set(a) | set(b))
    n = len(a)
    if n == 0:
        return None, None, None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    kappa = (po - pe) / (1 - pe) if pe != 1 else 1.0
    return po, pe, kappa


def main():
    df = read_any_encoding(FILE)

    df["ai_label"] = df["review"].apply(normalize)
    df["my_label"] = df["my_review"].apply(normalize)

    # 只对「机器判 False」的题做复核对比（True 的题没复核意义）
    bad = df[df["passed"] == False].copy()
    done = bad[bad["my_label"].notna()].copy()

    print(f"\n待复核 24 条，你已填 {len(done)} 条，还差 {24 - len(done)} 条")
    miss = bad[bad["my_label"].isna()]["id"].tolist()
    if miss:
        print(f"  ⚠ 还没填的题号：{miss}")

    if done.empty:
        raise SystemExit("还没填，先去 Excel 里填 my_review 列")

    ax = done["ai_label"].tolist()
    bx = done["my_label"].tolist()
    po, pe, kappa = cohens_kappa(ax, bx)

    print("\n" + "=" * 62)
    print("一、一致率")
    print("=" * 62)
    print(f"  样本数        : {len(done)} 条")
    print(f"  实际一致率 Po  : {po:.1%}  （{sum(1 for x, y in zip(ax, bx) if x == y)}/{len(done)} 条完全一致）")
    print(f"  随机一致率 Pe  : {pe:.1%}  （瞎猜也能碰上的比例）")
    print(f"  Cohen's Kappa : {kappa:.3f}")
    level = "几乎完美" if kappa > 0.8 else "高度一致" if kappa > 0.6 else "中等一致" if kappa > 0.4 else "一致性偏低"
    print(f"  解读          : {level}（一般 Kappa > 0.6 才算可用的标注质量）")

    print("\n" + "=" * 62)
    print("二、分歧清单（最值钱的部分 —— 每一条都该写进标注规范）")
    print("=" * 62)
    dis = done[done["ai_label"] != done["my_label"]]
    if dis.empty:
        print("  没有分歧，两份标注完全一致")
    for _, r in dis.iterrows():
        print(f"\n  id{int(r['id'])} [{r['layer']}]")
        print(f"    AI 判 : {r['ai_label']}  ← {str(r['review'])[:70]}")
        print(f"    你  判 : {r['my_label']}  ← {str(r['my_review'])[:70]}")

    print("\n" + "=" * 62)
    print("三、各自给出的类别分布")
    print("=" * 62)
    cmp = pd.DataFrame({"AI复核": pd.Series(ax).value_counts(),
                        "人工复核": pd.Series(bx).value_counts()}).fillna(0).astype(int)
    print(cmp.to_string())

    done_path = Path(FILE).parent / "review_done.csv"
    done.to_csv(done_path, index=False, encoding="utf-8-sig")
    print(f"\n[已保存] {done_path.name}（带 ai_label / my_label 两列，可直接给面试官看）")


if __name__ == "__main__":
    main()
