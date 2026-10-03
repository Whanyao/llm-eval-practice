"""
Day 2 练习 1：函数与异常处理
文件：D:\\Software\\llm-eval-practice\\d1_functions.py

目标：写出大模型评测脚本里最核心的两个基础函数。
评测脚本的骨架永远是这四步，每一步都是一个函数：
    读题  ->  调模型  ->  判分  ->  记录
          (call_llm)  (judge)

做完把运行结果发给我，我判卷。
"""


# ============================================================
# 题目 1：judge 判分函数（10 分钟）
# ============================================================
# 要求（按顺序判断）：
#   1. ai_answer 是 None 或空字符串 ""  ->  返回 None
#      （含义：这条回答无效——模型没返回内容，评测时要跳过，不能算错）
#   2. expected 出现在 ai_answer 文本里  ->  返回 True
#   3. 其他情况                          ->  返回 False
#
# 提示：用 if / elif / else；判断空可以用 `not ai_answer`
#      字符串包含判断用 `in`，比如 "2" in "答案是2" 结果是 True

#正确写法

def judge(ai_answer, expected):
    if not ai_answer:                 # None 或 "" 都算无效
        return None
    elif expected in ai_answer:
        return True
    else:
        return False


# ============================================================
# 题目 2：给模型调用加异常保护（10 分钟）
# ============================================================
# 下面这个函数模拟"调用大模型"：只要 prompt 里出现"报错"两个字就会抛异常
# （真实场景里，抛异常的原因会是：网络超时、限流 429、服务端 500 等）
def call_llm(prompt):
    if "报错" in prompt:
        raise TimeoutError("模型接口超时了")
    return "模型说：这是关于「" + prompt + "」的回答"


# 要求：写一个 safe_call 函数
#   1. 调用 call_llm(prompt)
#   2. 调用成功  ->  返回模型的回答文本
#   3. 抛出任何异常  ->  打印一行 "调用失败: xxx"（xxx 是异常信息），并返回 None
#
# 为什么必须这么写：你后面要批量跑几十条题目，某一条超时不能让整个脚本崩掉。
# 这就是你压测时的老思路——单点失败不能中断整轮测试。

#正确写法

def safe_call(prompt):
    try:
        return call_llm(prompt)       # 成功：把回答交出去
    except Exception as e:
        print("调用失败:", e)          # 失败：打印原因
        return None                    # 失败：返回 None，让上层知道这条无效



# ============================================================
# 自测区：不用改，直接运行看输出对不对
# 运行方式：终端里执行
#   cd D:\\Software\\llm-eval-practice
#   venv\\Scripts\\python.exe d1_functions.py
# ============================================================
if __name__ == "__main__":
    print("--- 题目 1 测试 ---")
    print(judge("答案是2", "2"))      # 期望 True
    print(judge("我不知道", "2"))     # 期望 False
    print(judge(None, "2"))          # 期望 None
    print(judge("", "2"))            # 期望 None

    print("--- 题目 2 测试 ---")
    print(safe_call("今天天气怎么样"))   # 期望：打印模型回答
    print(safe_call("故意让它报错"))     # 期望：打印 调用失败: 模型接口超时了  ->  None
