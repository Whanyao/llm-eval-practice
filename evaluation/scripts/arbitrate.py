# -*- coding: utf-8 -*-
r"""
arbitrate.py —— 双标注分歧仲裁 + 仲裁后指标重算

流程（这就是评测岗标准的标注质量流程）：
  1. AI 初标（review 列）      ┐
  2. 人工标注（my_review 列）  ├─> 背靠背双标注
  3. 算一致性 Kappa            ┘
  4. 分歧仲裁（本脚本 ARB 表）──> 形成定稿标签
  5. 按定稿标签重算准确率

仲裁规则（写进《标注规范 v1》）：
  【顺序优先级】超纲 > 幻觉 > 误杀 > 真错，命中即停
  规则A 超纲：把题给一个不给任何系统文档的资深领域专家，他答不出 → 超纲（题不该问）
  规则B 幻觉：编造了「具体但不存在」的信息（数值/年限/级次/字段名/规则名）且语气自信
             ≠ 错配（用了真实存在但场景不对的概念）——两者管理动作不同
  规则C 误杀：剥掉措辞后语义等价；只要缺关键得分点就不算误杀

运行：
  .\venv\Scripts\python.exe arbitrate.py
"""

from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[1] / "results"
SRC = str(BASE / "eval_results_v1_reviewed.csv")
OUT = str(BASE / "review_final.csv")

# ── 仲裁定稿表：id -> (定稿标签, 仲裁理由, 是否边界待定) ─────────────
ARB = {
    1:  ("超纲", "要求答出内部字段实现细节「不参与赋值运算」，非通用财务知识", False),
    2:  ("超纲", "要求答出产品功能名「折旧公式配置功能」", False),
    4:  ("超纲", "标准答案为产品功能定义，模型答的是通用折旧汇总概念", False),
    6:  ("超纲", "要求答出内部口径「下一年年折旧额」「月结后自动执行」", False),
    7:  ("超纲", "标准答案为产品实现口径，与会计准则口径不同层", False),
    8:  ("误杀", "结账/锁定/期间切换全答到，「系统进入下一个资产会计期间」≡「自动跳转到下一个账期」", False),
    9:  ("真错", "错配：把「资产模块↔核算模块对账」答成银行存款余额调节表——概念张冠李戴，但未编造具体不存在的信息", False),
    10: ("误杀", "撤销月结/回退期间/补录修改全部答到，仅措辞不同", False),
    12: ("真错", "答「价值变动仅涉及价值属性字段」，漏掉标准答案关键点「价值变动也可变动实物字段」", False),
    13: ("真错", "错配：把「资产转换」（固资↔投资性房地产/融资租赁/使用权资产，会计准则里有明确定义）答成类别变更/状态变更", True),
    15: ("真错", "错配：处置流程答成「报废/出售」，非「申请+执行 / 直接处置」", False),
    18: ("超纲", "问系统内两种盘点业务场景（多级流程/自助盘点）的产品划分，非通用盘点知识", True),
    19: ("超纲", "问产品功能「盘点人策略」的匹配机制，领域专家无法答出", False),
    22: ("真错", "漏掉核心得分点「不参与折旧」——正是题目第二问「在折旧上什么关系」的答案", False),
    28: ("超纲", "问两种调拨单生成模式的产品设计与适用场景", False),
    29: ("误杀", "「拆分前价值 = 各拆分后价值之和」与标准答案语义完全等价", False),
    32: ("真错", "老会计可推理（费用归集/分摊未完成不能关账），故不算超纲；模型未答到「卡住月结」", True),
    33: ("误杀", "「累计折旧≥应计提总额」与「使用年限(月)=已提摊销月数」在正常计提下是同一时刻，语义等价", True),
    34: ("超纲", "问产品功能「资产卡片数据检查」的固定范围（已审核且非减少）", False),
    35: ("超纲", "问系统状态枚举「盘点中/已取回」", False),
    37: ("真错", "把固定资产「次月起提」规则套到无形资产，答成下月起摊销", False),
    42: ("幻觉", "问内部配置，未表示不知道，反而编造参考折旧率", False),
    43: ("幻觉", "编造「500元/1000元」等具体阈值", False),
    44: ("幻觉", "编造「2-3级」等具体审批级次", False),
}


def read_any_encoding(path):
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc)
            print(f"[读取成功] {path} 编码 = {enc}")
            return df
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise SystemExit("两种编码都读不了")


def normalize(text):
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
    labels = sorted(set(a) | set(b))
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return po, pe, (po - pe) / (1 - pe) if pe != 1 else 1.0


def main():
    df = read_any_encoding(SRC)
    df["ai_label"] = df["review"].apply(normalize)
    df["human_label"] = df["my_review"].apply(normalize)

    # 补记：哪些是 AI 代填的（用户未填），对比时要剔除，避免"自己跟自己比"
    # 注意坑：pandas 读进来的空值是 float('nan')，而 nan 在 Python 里是 truthy —— 不能写 `if x`
    df["filled_by"] = df["human_label"].apply(
        lambda x: "人工" if isinstance(x, str) and x.strip() else "AI代填"
    )
    unlabeled = df[(df["passed"] == False) & (df["filled_by"] == "AI代填")]["id"].tolist()
    if unlabeled:
        print(f"[提示] 以下 badcase 用户未标，仲裁时按规则直接定稿：{unlabeled}")

    df["arbitrated"] = df["id"].map(lambda i: ARB.get(i, (None, "", False))[0])
    df["arb_reason"] = df["id"].map(lambda i: ARB.get(i, (None, "", False))[1])
    df["arb_borderline"] = df["id"].map(lambda i: ARB.get(i, (None, "", False))[2])

    # 定稿判分：只有「误杀」才翻案为通过；超纲/真错/幻觉 维持 False
    df["final_passed"] = df["passed"] | (df["arbitrated"] == "误杀")

    # ── 一致性：只用「人工真填的」子集，公平 ──
    bad = df[df["passed"] == False].copy()
    human = bad[bad["filled_by"] == "人工"].copy()
    ax, hx, rx = (human["ai_label"].tolist(), human["human_label"].tolist(),
                  human["arbitrated"].tolist())

    print("\n" + "=" * 64)
    print("一、标注一致性（仅用户真实填写的 %d 条）" % len(human))
    print("=" * 64)
    for name, arr in (("AI 初标 vs 仲裁定稿", ax), ("人工标注 vs 仲裁定稿", hx)):
        po, pe, k = cohens_kappa(arr, rx)
        print(f"  {name:<20} 一致率 {po:5.1%}   Kappa {k:+.3f}")
    po0, pe0, k0 = cohens_kappa(ax, hx)
    print(f"  {'AI 初标 vs 人工标注':<20} 一致率 {po0:5.1%}   Kappa {k0:+.3f}   ← 仲裁前的原始一致性")

    print("\n" + "=" * 64)
    print("二、仲裁后 badcase 归因分布（24 条）")
    print("=" * 64)
    print(bad["arbitrated"].value_counts().to_string())

    print("\n" + "=" * 64)
    print("三、仲裁后的准确率（这才是应该写进报告的数字）")
    print("=" * 64)
    n, n_pass = len(df), int(df["final_passed"].sum())
    n_oob = int((df["arbitrated"] == "超纲").sum())
    n_mis = int((df["arbitrated"] == "误杀").sum())
    print(f"  原始准确率（纯关键词判分）      : {n_pass - n_mis}/{n} = {(n_pass - n_mis) / n:.1%}")
    print(f"  修正误杀 {n_mis} 条后                : {n_pass}/{n} = {n_pass / n:.1%}")
    print(f"  再剔除超纲 {n_oob} 题后的有效准确率 : {n_pass}/{n - n_oob} = {n_pass / (n - n_oob):.1%}")

    print("\n" + "=" * 64)
    print("四、人工标注比 AI 初标更接近仲裁定稿的条目（AI 该学的）")
    print("=" * 64)
    for _, r in human.iterrows():
        if r["ai_label"] != r["arbitrated"] and r["human_label"] == r["arbitrated"]:
            print(f"  id{int(r['id'])}  人工={r['human_label']}  AI初标={r['ai_label']}  → 仲裁支持人工")

    print("\n" + "=" * 64)
    print("五、边界待定（这几条你可以推翻我）")
    print("=" * 64)
    for _, r in df[df["arb_borderline"] == True].iterrows():
        print(f"  id{int(r['id'])} 我判「{r['arbitrated']}」｜你判「{r['human_label']}」｜{r['arb_reason'][:56]}")

    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n[已保存] {OUT}（含 ai_label / human_label / arbitrated / final_passed 四列）")


if __name__ == "__main__":
    main()
