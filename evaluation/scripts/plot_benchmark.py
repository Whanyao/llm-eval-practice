# -*- coding: utf-8 -*-
"""
生成 C-Eval 双模型对比图（图1 总分 / 图2 分科目）。
零第三方依赖：标准库手写 SVG，再由本地浏览器转成 PNG。
用法： python evaluation/scripts/plot_benchmark.py
"""
import csv, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(BASE, "results")
FIGDIR = os.path.join(BASE, "figures")
os.makedirs(FIGDIR, exist_ok=True)

FONT = "Microsoft YaHei, Segoe UI, SimHei, sans-serif"
INK, MUTED, GRID = "#1F2329", "#6B7280", "#E5E7EB"
C_DS, C_QW = "#2E6FD9", "#E8952F"
NAME_DS = "DeepSeek-V3 (deepseek-chat)"
NAME_QW = "Qwen3-30B-A3B-Instruct-2507"

SUBJECT_CN = {
    "accountant": "会计", "tax_accountant": "税务会计", "college_economics": "大学经济学",
    "business_administration": "工商管理", "college_programming": "大学编程",
    "law": "法律", "logic": "逻辑",
}


def load(fn):
    with open(os.path.join(RESULTS, fn), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def passed(r):
    return str(r["passed"]).strip().lower() == "true"


def summarize(rows):
    ok = sum(1 for r in rows if passed(r))
    per = {}
    for r in rows:
        d = per.setdefault(r["subject"], [0, 0])
        d[1] += 1
        if passed(r):
            d[0] += 1
    return len(rows), ok, per


ds, qw = load("benchmark_deepseek.csv"), load("benchmark_qwen.csv")
n, ds_ok, ds_per = summarize(ds)
_, qw_ok, qw_per = summarize(qw)
ds_acc, qw_acc = ds_ok / n * 100, qw_ok / n * 100
print("DeepSeek %d/%d = %.1f%%   Qwen %d/%d = %.1f%%   差 %.1fpp"
      % (ds_ok, n, ds_acc, qw_ok, n, qw_acc, ds_acc - qw_acc))

H = 'font-family="%s"' % FONT


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fig1():
    W, Hh = 1000, 680
    L, R, T, B = 110, 60, 120, 150
    px0, py1 = L, Hh - B
    pw, ph = W - L - R, py1 - T
    def ytop(v):
        return py1 - v / 100.0 * ph

    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, Hh, W, Hh),
         '<rect width="%d" height="%d" fill="#FFFFFF"/>' % (W, Hh),
         '<text x="%.0f" y="50" text-anchor="middle" font-size="27" font-weight="bold" fill="%s" %s>两款模型在 C-Eval 100 题子集上的总准确率</text>' % (W / 2, INK, H),
         '<text x="%.0f" y="80" text-anchor="middle" font-size="15" fill="%s" %s>同一题库（7 科目 / 100 题） · 同一提示词 · temperature=0.0 · 取单次运行结果</text>' % (W / 2, MUTED, H)]

    for v in range(0, 101, 20):
        y = ytop(v)
        s.append('<line x1="%d" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (px0, y, px0 + pw, y, GRID))
        s.append('<text x="%d" y="%.1f" text-anchor="end" font-size="14" fill="%s" %s>%d%%</text>' % (px0 - 16, y + 5, MUTED, H, v))
    s.append('<line x1="%d" y1="%d" x2="%.1f" y2="%d" stroke="#9CA3AF" stroke-width="1.5"/>' % (px0, py1, px0 + pw, py1))

    bw, cxs = 130, [350.0, 700.0]
    for cx, acc, ok, col, name in ((cxs[0], ds_acc, ds_ok, C_DS, NAME_DS), (cxs[1], qw_acc, qw_ok, C_QW, NAME_QW)):
        x, y = cx - bw / 2, ytop(acc)
        s.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" fill="%s" rx="3"/>' % (x, y, bw, py1 - y, col))
        s.append('<text x="%.0f" y="%.1f" text-anchor="middle" font-size="30" font-weight="bold" fill="#FFFFFF" %s>%.1f%%</text>' % (cx, y + 46, H, acc))
        s.append('<text x="%.0f" y="%.1f" text-anchor="middle" font-size="15" fill="#EAF0FB" %s>%d / %d 题</text>' % (cx, y + 72, H, ok, n))
        s.append('<text x="%.0f" y="%d" text-anchor="middle" font-size="16" fill="%s" %s>%s</text>' % (cx, py1 + 34, INK, H, esc(name)))

    yl = 150.0
    s.append('<line x1="%.0f" y1="%.0f" x2="%.0f" y2="%.0f" stroke="#9CA3AF" stroke-width="1.2" stroke-dasharray="5 4"/>' % (cxs[0], yl, cxs[1], yl))
    s.append('<rect x="%.0f" y="%.0f" width="144" height="32" rx="16" fill="#FFF4E5" stroke="#F0C48A"/>' % (W / 2 - 72, yl - 16))
    s.append('<text x="%.0f" y="%.0f" text-anchor="middle" font-size="16" font-weight="bold" fill="#B26A00" %s>相差 %.1fpp</text>' % (W / 2, yl + 6, H, ds_acc - qw_acc))
    s.append('<text x="%d" y="%d" font-size="14" fill="%s" %s>算式：DeepSeek %d÷%d=%.1f%%　|　Qwen %d÷%d=%.1f%%　|　相减 = %.1fpp（共 100 题，1 题 = 1pp）</text>' % (px0, Hh - 62, MUTED, H, ds_ok, n, ds_acc, qw_ok, n, qw_acc, ds_acc - qw_acc))
    s.append('<text x="%d" y="%d" font-size="14" fill="%s" %s>pp = 百分点，两数直接相减；若说「高出百分之几」则是 (%.1f−%.1f)÷%.1f = %.2f%%，两种说法别混用。</text>' % (px0, Hh - 36, MUTED, H, ds_acc, qw_acc, qw_acc, (ds_acc - qw_acc) / qw_acc * 100))
    s.append('</svg>')
    return "\n".join(s)


def fig2():
    W, Hh = 1200, 750
    L, R, T, B = 90, 45, 168, 130
    px0, py1 = L, Hh - B
    pw, ph = W - L - R, py1 - T
    def ytop(v):
        return py1 - v / 100.0 * ph

    order = sorted(ds_per.keys(), key=lambda k: -ds_per[k][1])
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, Hh, W, Hh),
         '<rect width="%d" height="%d" fill="#FFFFFF"/>' % (W, Hh),
         '<text x="%.0f" y="48" text-anchor="middle" font-size="27" font-weight="bold" fill="%s" %s>分科目准确率对比（按题目数从多到少排列）</text>' % (W / 2, INK, H),
         '<text x="%.0f" y="78" text-anchor="middle" font-size="15" fill="%s" %s>柱顶数字为该科目准确率；横轴括号内是题目数</text>' % (W / 2, MUTED, H)]

    lx = px0 + 8
    s.append('<rect x="%d" y="98" width="16" height="16" fill="%s" rx="2"/>' % (lx, C_DS))
    s.append('<text x="%d" y="112" font-size="14.5" fill="%s" %s>%s</text>' % (lx + 24, INK, H, esc(NAME_DS)))
    lx2 = lx + 330
    s.append('<rect x="%d" y="98" width="16" height="16" fill="%s" rx="2"/>' % (lx2, C_QW))
    s.append('<text x="%d" y="112" font-size="14.5" fill="%s" %s>%s</text>' % (lx2 + 24, INK, H, esc(NAME_QW)))

    for v in range(0, 101, 20):
        y = ytop(v)
        s.append('<line x1="%d" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="1"/>' % (px0, y, px0 + pw, y, GRID))
        s.append('<text x="%d" y="%.1f" text-anchor="end" font-size="13.5" fill="%s" %s>%d%%</text>' % (px0 - 14, y + 5, MUTED, H, v))
    s.append('<line x1="%d" y1="%d" x2="%.1f" y2="%d" stroke="#9CA3AF" stroke-width="1.5"/>' % (px0, py1, px0 + pw, py1))

    gw = pw / len(order)
    bw, gap = 46, 8
    for i, subj in enumerate(order):
        x0 = px0 + i * gw
        cnt = ds_per[subj][1]
        d_a = ds_per[subj][0] / cnt * 100
        q_a = qw_per[subj][0] / cnt * 100
        for j, acc, col in ((0, d_a, C_DS), (1, q_a, C_QW)):
            x = x0 + (gw - (bw * 2 + gap)) / 2 + j * (bw + gap)
            y = ytop(acc)
            s.append('<rect x="%.1f" y="%.1f" width="%d" height="%.1f" fill="%s" rx="2"/>' % (x, y, bw, py1 - y, col))
            s.append('<text x="%.1f" y="%.1f" text-anchor="middle" font-size="13" font-weight="bold" fill="%s" %s>%.1f</text>' % (x + bw / 2, y - 9, INK, H, acc))
        s.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="15" fill="%s" %s>%s</text>' % (x0 + gw / 2, py1 + 30, INK, H, esc(SUBJECT_CN.get(subj, subj))))
        s.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="13" fill="%s" %s>（%d 题）</text>' % (x0 + gw / 2, py1 + 52, MUTED, H, cnt))
        dcol = "#B26A00" if abs(d_a - q_a) >= 10 else MUTED
        s.append('<text x="%.1f" y="%d" text-anchor="middle" font-size="13" font-weight="bold" fill="%s" %s>%+.1fpp</text>' % (x0 + gw / 2, py1 + 76, dcol, H, d_a - q_a))

    s.append('<text x="%d" y="%d" font-size="13.5" fill="%s" %s>读图提醒：题目少的科目天然波动大 —— 法律、逻辑各 6 题（1 题 = 100÷6 = 16.7pp）；会计 28 题（1 题 = 100÷28 ≈ 3.6pp）。</text>' % (px0, Hh - 30, MUTED, H))
    s.append('<text x="%d" y="%d" font-size="13.5" fill="%s" %s>每组最后一行为两模型之差（DeepSeek − Qwen），正数表示 DeepSeek 更高。</text>' % (px0, Hh - 9, MUTED, H))
    s.append('</svg>')
    return "\n".join(s)


for name, svg in (("fig1_total_score", fig1()), ("fig2_subject_compare", fig2())):
    p = os.path.join(FIGDIR, name + ".svg")
    with open(p, "w", encoding="utf-8") as f:
        f.write(svg)
    print("written:", p, len(svg), "bytes")
