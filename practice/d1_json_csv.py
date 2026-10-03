"""
Day 2 练习 2：json / 文件读写 / CSV
文件：D:\\Software\\llm-eval-practice\\d1_json_csv.py

为什么要学这个 —— 评测脚本的输入输出全是这两种格式：
    读：评测题目（question + expected）通常存成 CSV
    写：评测结果（模型回答 + 判分）通常存成 CSV 或 JSON
你熟 JSON（接口测试天天见），现在只是换成 Python 的写法。

做完把终端输出发我，我判卷。
"""

import json
import csv


# ============================================================
# 题目 1：dict <-> JSON 文件（10 分钟）
# ============================================================
# 要求：
#   1. 把下面 sample_result 这个 dict 写入 result.json
#      用 json.dump(数据, 文件对象, ensure_ascii=False, indent=2)
#   2. 再从 result.json 读回来，取出 "model_answer" 字段并打印
#      用 json.load(文件对象)
#
# 提示（文件操作的固定套路是 with open，用完自动关文件）：
#   写：with open("result.json", "w", encoding="utf-8") as f:
#           json.dump(数据, f, ensure_ascii=False, indent=2)
#   读：with open("result.json", "r", encoding="utf-8") as f:
#           data = json.load(f)
#       print(data["model_answer"])
#
# ensure_ascii=False 的作用：不加它，中文会被转成 \u4e2d\u6587 这种转义码
sample_result = {
    "id": 1,
    "question": "资产折旧的会计处理方法有哪些？",
    "model_answer": "主要有直线法、工作量法、双倍余额递减法、年数总和法。",
    "judge": True,
}
# 把下面 sample_result 这个 dict 写入 result.json
with open("result.json", "w", encoding="utf-8") as f:
    json.dump(sample_result, f, ensure_ascii=False, indent=2)
# 从 result.json 读回来，取出 "model_answer" 字段并打印
with open("result.json", "r", encoding="utf-8") as f:
    data = json.load(f)
print(data["model_answer"])

# ============================================================
# 题目 2：写 CSV 再读回来（15 分钟）
# ============================================================
# 要求：
#   1. 用 csv.writer 生成 questions.csv，表头是 question,expected
#      写入 3 行评测数据（题目 + 期望答案，内容自己编，财务相关最好）
#   2. 用 csv.DictReader 读回来，逐行打印 "问题: xxx | 期望: xxx"
#
# 提示：
#   写：with open("questions.csv", "w", encoding="utf-8-sig", newline="") as f:
#           w = csv.writer(f)
#           w.writerow(["question", "expected"])          # 表头
#           w.writerows([["题目1", "答案1"], ["题目2", "答案2"]])
#   读：with open("questions.csv", "r", encoding="utf-8-sig") as f:
#           for row in csv.DictReader(f):
#               print(row["question"], row["expected"])
#
# encoding 用 utf-8-sig 的作用：让 Excel 直接双击打开不乱码（你以后要在 Excel 里看评测结果）
# newline="" 的作用：防止 Windows 下 CSV 多出空行

# 1. 写入 questions.csv
with open("questions.csv", "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    # 写入表头
    w.writerow(["question", "expected"])
    # 写入3行财务评测数据
    w.writerows([
        ["什么是权责发生制？", "权责发生制是以权利和责任的发生来确认收入和费用，而不以实际收付现金为标准。"],
        ["流动比率计算公式是什么？", "流动比率 = 流动资产 ÷ 流动负债，用来衡量企业短期偿债能力。"],
        ["哪些属于期间费用？", "期间费用包含管理费用、销售费用、财务费用。"]
    ])

# 2. 用DictReader读取并按格式打印
with open("questions.csv", "r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        print(f"问题：{row['question']} | 期望：{row['expected']}")

