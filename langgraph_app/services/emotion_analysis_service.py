#"""
#新版情绪识别服务（V2 - 稳定增强版）
#包含：
#- STEP1 情绪原子句拆解（重试 + 规则兜底 + 输出修复）
#- STEP2 GoEmotions 固定标签计数（输出修复）
#- STEP3 多模型协商（不改）
#"""
#
#import json
#import re
#import ast
#import sys
#import os
#from typing import Any, Dict, List, Optional, Tuple
#from urllib.parse import unquote
#
#_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
#_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
#if _PROJECT_ROOT not in sys.path:
#    sys.path.insert(0, _PROJECT_ROOT)
#
#from utils.functions import call_llm, unload_model
#
#
## ======================================================
## GoEmotions 标签集（固定 27 维）
## ======================================================
#GOEMOTIONS_LABELS = [
#    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
#    "confusion", "curiosity", "desire", "disappointment", "disapproval",
#    "disgust", "embarrassment", "excitement", "fear", "gratitude",
#    "grief", "joy", "love", "nervousness", "optimism", "pride",
#    "realization", "relief", "remorse", "sadness", "surprise", "neutral"
#]
#
#
## ======================================================
## JSON 抽取（括号配对，鲁棒）
## ======================================================
#def _extract_and_parse_json(text: str, log_prefix: str = "") -> Optional[Any]:
#    if not text:
#        return None
#
#    try:
#        if "%" in text:
#            text = unquote(text)
#    except Exception:
#        pass
#
#    text = text.replace("“", '"').replace("”", '"')
#    text = re.sub(r"```(?:json)?", "", text)
#    text = text.replace("```", "")
#    text = re.sub(r"//.*", "", text)
#
#    start = None
#    stack = []
#    pairs = {"{": "}", "[": "]"}
#    rev = {"}": "{", "]": "["}
#
#    for i, ch in enumerate(text):
#        if ch in pairs:
#            if start is None:
#                start = i
#            stack.append(ch)
#        elif ch in rev and stack and stack[-1] == rev[ch]:
#            stack.pop()
#            if not stack and start is not None:
#                candidate = text[start:i + 1]
#                try:
#                    return json.loads(candidate)
#                except Exception:
#                    try:
#                        return ast.literal_eval(candidate)
#                    except Exception:
#                        print(f"[{log_prefix}] ⚠️ JSON 抽取失败，片段前200字符:\n{candidate[:200]}")
#                        return None
#
#    print(f"[{log_prefix}] ⚠️ 未找到完整 JSON，原始输出前200字符:\n{text[:200]}")
#    return None
#
#
## ======================================================
## JSON 输出修复器（仅修格式，不改语义）
## ======================================================
#def _repair_json_with_llm(raw_text: str, log_prefix: str = "") -> Optional[Any]:
#    REPAIR_PROMPT = f"""
#你是一个 JSON 修复器。
#下面内容包含一个“接近 JSON 但不合法”的结构。
#
#请你：
#1. 不改变原有语义
#2. 不添加任何新信息
#3. 仅将其修复为【合法 JSON】
#4. 只输出 JSON，不要解释
#
#原始内容：
#{raw_text}
#""".strip()
#
#    try:
#        resp, _ = call_llm(
#            "qwen2-7b",
#            [
#                {"role": "system", "content": "你只输出 JSON"},
#                {"role": "user", "content": REPAIR_PROMPT}
#            ]
#        )
#        return _extract_and_parse_json(resp, f"{log_prefix}-REPAIR")
#    except Exception as e:
#        print(f"[{log_prefix}] ⚠️ JSON 修复失败: {e}")
#        return None
#
#
### ======================================================
### STEP 1：情绪原子句拆解（增强）
### ======================================================
##def _rewrite_to_emotion_atoms(query: str) -> Dict[str, Any]:
##    PROMPT = """
##你是一个 JSON 生成器，只负责生成 JSON 数据。
##
##你的唯一任务是：  
##把用户混乱或复合的自然语言表达，拆解为便于情绪标注的“情绪原子”列表。
##
##【强制规则】
##1. 你只能输出一个 JSON 对象
##2. 不允许输出任何解释、说明、分析、建议或安慰性文字
##3. 不允许出现 ```、Human:、注释(//)、省略号(...)
##4. 所有内容必须严格符合下方 JSON Schema
##5. 不允许新增任何 schema 之外的字段
##6. 如果无法生成合法 JSON，请返回：
##   {{ "error": "invalid_output" }}
##
##【JSON Schema】
##{{
##  "rewrites": [
##    "string"
##  ]
##}}
##
##【任务要求】
##- 将用户表达拆解成 1–5 条“情绪原子句”
##- 每一条只表达一种独立、明确的情绪 / 感受 / 内心状态
##- 保持用户原有的情绪强弱和语气，不得弱化或夸张
##- 使用简短、自然的中文陈述句
##- 不要引入新的情绪、原因分析或价值判断
##- 不要输出空数组
##
##【示例】
##用户输入：
##我知道这段关系已经结束了，但心里还是很难接受，总觉得有些遗憾，也对未来有点迷茫。
##
##正确输出：
##{{
##  "rewrites": [
##    "难以接受一段关系已经结束的事实",
##    "内心仍然对这段关系感到遗憾",
##    "对未来的情感走向感到迷茫"
##  ]
##}}
##
##【用户输入】
##{query}
##""".strip().format(query=query)
##
##    def call_once(tag: str):
##        print(f"[EMO-ATOM] 🔄 情绪原子句拆解（{tag}）")
##        resp, _ = call_llm(
##            "qwen2-7b",
##            [
##                {"role": "system", "content": "你只输出 JSON"},
##                {"role": "user", "content": PROMPT}
##            ]
##        )
##
##        parsed = _extract_and_parse_json(resp, "EMO-ATOM")
##        if isinstance(parsed, dict):
##            for k in ("rewrites", "rewires"):
##                if k in parsed and isinstance(parsed[k], list):
##                    return parsed[k]
##
##        print("[EMO-ATOM] 🛠️ 尝试 JSON 修复")
##        repaired = _repair_json_with_llm(resp, "EMO-ATOM")
##        if isinstance(repaired, dict):
##            for k in ("rewrites", "rewires"):
##                if k in repaired and isinstance(repaired[k], list):
##                    print("[EMO-ATOM] ✅ JSON 修复成功")
##                    return repaired[k]
##
##        return None
##
##    atoms = call_once("首次")
##    if atoms:
##        return {"rewrites": atoms}
##
##    atoms = call_once("重试")
##    if atoms:
##        return {"rewrites": atoms, "_retry": True}
##
##    print("[EMO-ATOM] ⚠️ 启用规则兜底（标点拆句）")
##    parts = re.split(r"[。！？!?；;，,\n]", query)
##    atoms = [p.strip() for p in parts if p and len(p.strip()) > 2]
##    return {"rewrites": atoms or [query.strip()], "_rule_fallback": True}
#
#import re
#from typing import Any, Dict, List, Optional
#
#
## ======================================================
## STEP 1：情绪原子句拆解（工程稳定版）
## ======================================================
#def _rewrite_to_emotion_atoms(query: str) -> Dict[str, Any]:
#    """
#    将用户输入拆解为情绪原子句。
#    - 输出结构固定：{"rewrite": List[str]}
#    - JSON 结构完全由程序保证
#    - 模型只负责生成“纯文本原子句”
#    """
#
#    PROMPT = f"""
#你是一个情绪原子句拆解器。
#
#你的任务是：
#把用户输入拆解为 1–5 条“情绪原子句”。
#
#【强制规则】
#1. 只输出拆解后的句子本身
#2. 每一行只写一句话
#3. 不要输出 JSON
#4. 不要输出序号、符号、引号、解释、空行
#5. 不要输出除句子以外的任何内容
#6. 使用简短、自然的中文陈述句
#7. 不得包含控制字符或特殊符号
#
#【任务要求】
#- 每句话只表达一种情绪 / 感受 / 内心状态
#- 保持原有情绪强度，不得弱化或夸张
#- 不引入新的情绪、原因分析或价值判断
#
#【示例】
#
#输入：
#我知道这段关系已经结束了，但心里还是很难接受，总觉得有些遗憾，也对未来有点迷茫。
#
#输出：
#难以接受一段关系已经结束的事实
#内心仍然对这段关系感到遗憾
#对未来的情感走向感到迷茫
#
#【用户输入】
#{query}
#""".strip()
#
#    # --------------------------------------------------
#    # 单次调用
#    # --------------------------------------------------
#    def call_once(tag: str) -> Optional[List[str]]:
#        print(f"[EMO-ATOM] 🔄 情绪原子句拆解（{tag}）")
#
#        resp, _ = call_llm(
#            "qwen2-7b",
#            [
#                {"role": "system", "content": "你只输出拆解后的句子文本"},
#                {"role": "user", "content": PROMPT}
#            ]
#        )
#
#        if not resp or not isinstance(resp, str):
#            return None
#
#        # === 1️⃣ 清洗控制字符（关键） ===
#        text = re.sub(r'[\x00-\x1f\x7f]', '', resp)
#
#        # === 2️⃣ 按行拆分 ===
#        lines = [
#            line.strip()
#            for line in text.splitlines()
#            if line.strip()
#        ]
#
#        # === 3️⃣ 过滤非法或异常句子 ===
#        atoms: List[str] = []
#        for line in lines:
#            # 过短、过长直接丢弃
#            if len(line) < 3 or len(line) > 50:
#                continue
#            # 明显非情绪陈述的过滤
#            if any(x in line for x in ("输出", "示例", "输入", "{", "}", "[", "]")):
#                continue
#            atoms.append(line)
#
#        # 数量约束
#        if 1 <= len(atoms) <= 5:
#            return atoms
#
#        return None
#
#    # --------------------------------------------------
#    # 主流程
#    # --------------------------------------------------
#    atoms = call_once("首次")
#    if atoms:
#        return {"rewrite": atoms}
#
#    atoms = call_once("重试")
#    if atoms:
#        return {
#            "rewrite": atoms,
#            "_retry": True
#        }
#
#    # --------------------------------------------------
#    # 规则兜底（最后防线）
#    # --------------------------------------------------
#    print("[EMO-ATOM] ⚠️ 启用规则兜底（标点拆句）")
#
#    parts = re.split(r"[。！？!?；;，,\n]", query)
#    atoms = [
#        p.strip()
#        for p in parts
#        if p and len(p.strip()) > 2
#    ]
#
#    return {
#        "rewrite": atoms[:5] or [query.strip()],
#        "_rule_fallback": True
#    }
#
#
## ======================================================
## STEP 2：GoEmotions 标签计数（增强，单次调用）
## ======================================================
#def _goemotions_tagging_and_summary(query: str, atoms_json: Dict[str, Any]) -> Dict[str, Any]:
#    counts = {label: 0 for label in GOEMOTIONS_LABELS}
#
#    PROMPT = """
#你是一个 JSON 生成器，只负责生成 JSON 数据。
#
#你的任务是：
#基于 GoEmotions 标签集，对情绪原子列表进行情绪标注并给出汇总。
#
#【GoEmotions 标签集】
#{labels}
#
#【用户原始表达】
#{query}
#
#【情绪原子列表】
#{atoms}
#
#【JSON Schema】
#{{
#  "goemotions_summary": {{
#    "emotion_label": 0
#  }},
#  "sentiment": "positive|neutral|negative",
#  "has_conflict": false,
#  "sentences": [
#    {{
#      "text": "string",
#      "labels": ["emotion_label"]
#    }}
#  ]
#}}
#""".strip()
#
#    p = PROMPT.format(
#        labels=", ".join(GOEMOTIONS_LABELS),
#        query=query,
#        atoms=json.dumps(atoms_json, ensure_ascii=False)
#    )
#
#    resp, _ = call_llm(
#        "qwen2-7b",
#        [
#            {"role": "system", "content": "你只输出 JSON"},
#            {"role": "user", "content": p}
#        ]
#    )
#
#    parsed = _extract_and_parse_json(resp, "EMO-GOEMO")
#    if not isinstance(parsed, dict):
#        parsed = _repair_json_with_llm(resp, "EMO-GOEMO")
#
#    if not isinstance(parsed, dict):
#        return {
#            "goemotions_summary": {},
#            "sentiment": "neutral",
#            "has_conflict": False,
#            "sentences": []
#        }
#
#    for k, v in parsed.get("goemotions_summary", {}).items():
#        if k in counts:
#            counts[k] += int(v)
#
#    return parsed
## ======================================================
## STEP 3：多模型协商（A↔B 多轮 + C 仲裁）
## ======================================================
#def _negotiate_8d_vector(
#    query: str,
#    atoms_json: Dict[str, Any],
#    goemo_json: Dict[str, Any]
#) -> Tuple[str, bool]:
#    """
#    返回：
#    - vector_json_str: Plutchik 8 维情绪 JSON 数组字符串
#    - consensus: 是否由快系统达成一致
#    """
#
#    print("\n🧠 [STEP3 开始] 多模型协商输入：")
#    print("   原问题：", query)
#    print("   情绪标签：", goemo_json["goemotions_summary"])
#
#    # -----------------------------
#    # Plutchik 八维情绪空间
#    # -----------------------------
#    EMOTIONS = [
#        "joy", "acceptance", "fear", "surprise",
#        "sadness", "disgust", "anger", "anticipation"
#    ]
#
#    # -----------------------------
#    # 协商超参数
#    # -----------------------------
#    MAX_ROUNDS = 3     # 每阶段最大协商轮次
#    DELTA = 2.0        # 差异阈值 δ（最大维度差）
#
#    # -----------------------------
#    # 公共上下文（包含 STEP2 结果）
#    # -----------------------------
#    BASE_CONTEXT = f"""
#用户原始输入：
#{query}
#
#GoEmotions 情绪标签统计：
#{json.dumps(goemo_json["goemotions_summary"], ensure_ascii=False)}
#""".strip()
#
#    # -----------------------------
#    # Prompt 定义（方法论对齐）
#    # -----------------------------
#    PROMPT_GENERATE = f"""
#你是高级情绪分析专家。
#请基于以下信息，对 Plutchik 八维情绪进行 1–10 分打分：
#
#情绪维度：
#{", ".join(EMOTIONS)}
#
#{BASE_CONTEXT}
#
#要求：
#1. 必须输出 8 个维度
#2. 每个维度只出现一次
#3. 分数范围 1–10
#4. 只输出 JSON 数组，不要解释
#
#输出格式：
#[
#  {{"emotion": "joy", "score": 5}},
#  ...
#]
#""".strip()
#
#    PROMPT_EVALUATE = f"""
#你是理性评估者。
#请审查并修正下面的候选情绪打分结果。
#
#{BASE_CONTEXT}
#
#候选结果：
#{{candidate}}
#
#审查要点：
#- 是否符合文本与情绪标签统计
#- 情绪强度是否过高或过低
#- 是否存在明显冲突
#
#要求：
#1. 直接输出修正后的最终结果
#2. 必须包含 8 个维度
#3. 分数范围 1–10
#4. 只输出 JSON 数组
#""".strip()
#
#    PROMPT_ARBITRATE = f"""
#你是慢系统仲裁者。
#快系统未达成一致，请综合判断给出最终结果。
#
#{BASE_CONTEXT}
#
#快系统 A（qwen2-1.5b）结果：
#{{ra}}
#
#快系统 B（qwen2-7b）结果：
#{{rb}}
#
#要求：
#1. 输出最终 Plutchik 八维情绪评分
#2. 每个维度只出现一次
#3. 分数范围 1–10
#4. 只输出 JSON 数组
#""".strip()
#
#    # -----------------------------
#    # 工具函数
#    # -----------------------------
#    def _call(model: str, prompt: str, tag: str):
#        resp, _ = call_llm(
#            model,
#            [
#                {"role": "system", "content": "你只输出 JSON"},
#                {"role": "user", "content": prompt}
#            ]
#        )
#        return _extract_and_parse_json(resp, tag)
#
#    def _max_diff(v1, v2) -> float:
#        diffs = []
#        for a, b in zip(v1, v2):
#            try:
#                diffs.append(abs(float(a["score"]) - float(b["score"])))
#            except Exception:
#                diffs.append(10.0)
#        return max(diffs) if diffs else 10.0
#
#    # ==================================================
#    # 阶段一：A → B（qwen2-1.5b → qwen2-7b）
#    # ==================================================
#    last_A = None
#    last_B = None
#
#    for t in range(MAX_ROUNDS):
#        print(f"[EMO-NEGOTIATE] 🔄 阶段1 A→B 轮次 {t+1}")
#
#        R_A = _call("qwen2-1.5b", PROMPT_GENERATE, "EMO-A-GEN")
#        if not R_A:
#            continue
#
#        eval_prompt = PROMPT_EVALUATE.replace(
#            "{candidate}", json.dumps(R_A, ensure_ascii=False)
#        )
#        F_B = _call("qwen2-7b", eval_prompt, "EMO-B-EVAL")
#
#        if R_A and F_B:
#            d = _max_diff(R_A, F_B)
#            print(f"[EMO-NEGOTIATE] 阶段1 最大差异 = {d:.2f}")
#            if d <= DELTA:
#                print("[EMO-NEGOTIATE] ✅ 阶段1 A/B 达成一致")
#                return json.dumps(F_B, ensure_ascii=False), True
#
#        last_A, last_B = R_A, F_B
#
#    # ==================================================
#    # 阶段二：B → A（qwen2-7b → qwen2-1.5b）
#    # ==================================================
#    for t in range(MAX_ROUNDS):
#        print(f"[EMO-NEGOTIATE] 🔄 阶段2 B→A 轮次 {t+1}")
#
#        R_B = _call("qwen2-7b", PROMPT_GENERATE, "EMO-B-GEN")
#        if not R_B:
#            continue
#
#        eval_prompt = PROMPT_EVALUATE.replace(
#            "{candidate}", json.dumps(R_B, ensure_ascii=False)
#        )
#        F_A = _call("qwen2-1.5b", eval_prompt, "EMO-A-EVAL")
#
#        if R_B and F_A:
#            d = _max_diff(R_B, F_A)
#            print(f"[EMO-NEGOTIATE] 阶段2 最大差异 = {d:.2f}")
#            if d <= DELTA:
#                print("[EMO-NEGOTIATE] ✅ 阶段2 B/A 达成一致")
#                return json.dumps(F_A, ensure_ascii=False), True
#
#        last_A, last_B = F_A, R_B
#
#    # ==================================================
#    # 阶段三：慢系统仲裁（DeepSeek-R1）
#    # ==================================================
#    print("[EMO-NEGOTIATE] ⚖️ 快系统未达成一致，启动慢系统仲裁")
#
#    arb_prompt = PROMPT_ARBITRATE \
#        .replace("{ra}", json.dumps(last_A, ensure_ascii=False)) \
#        .replace("{rb}", json.dumps(last_B, ensure_ascii=False))
#
#    R_C = _call("DeepSeek-R1", arb_prompt, "EMO-C-ARB")
#
#    if R_C:
#        return json.dumps(R_C, ensure_ascii=False), False
#
#    # 兜底
#    fallback = last_B or last_A
#    return json.dumps(fallback, ensure_ascii=False), False
#
## ======================================================
## 主入口（不变）
## ======================================================
#def run_emotion_analysis(query: str) -> Tuple[str, bool, Dict[str, Any]]:
#    print("\n📊 [阶段1-3] 新版情绪识别开始（三步分析法）...")
#
#    atoms = _rewrite_to_emotion_atoms(query)
#
#    print("\n✅ [STEP1 完成] 最终情绪原子句：")
#    for i, a in enumerate(atoms["rewrites"], 1):
#        print(f"   [{i}] {a}")
#
#    goemo = _goemotions_tagging_and_summary(query, atoms)
#
#    vector, consensus = _negotiate_8d_vector(query, atoms, goemo)
#
#    return vector, consensus, {
#        "emotion_atoms": atoms,
#        "goemotions": goemo,
#        "consensus": consensus
#    }
"""
新版情绪识别服务（V2 - 稳定增强版）
包含：
- STEP1 情绪原子句拆解（重试 + 规则兜底 + 输出修复）
- STEP2 GoEmotions 固定标签计数（输出修复）
- STEP3 多模型协商（不改）
"""

import json
import re
import ast
import sys
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from utils.functions import call_llm, unload_model


# ======================================================
# GoEmotions 标签集（固定 27/28 维，保持你的原样）
# ======================================================
GOEMOTIONS_LABELS = [
    "admiration", "amusement", "anger", "annoyance", "approval", "caring",
    "confusion", "curiosity", "desire", "disappointment", "disapproval",
    "disgust", "embarrassment", "excitement", "fear", "gratitude",
    "grief", "joy", "love", "nervousness", "optimism", "pride",
    "realization", "relief", "remorse", "sadness", "surprise", "neutral"
]


# ======================================================
# JSON 抽取（括号配对，鲁棒）
# ======================================================
def _extract_and_parse_json(text: str, log_prefix: str = "") -> Optional[Any]:
    if not text:
        return None

    try:
        if "%" in text:
            text = unquote(text)
    except Exception:
        pass

    text = text.replace("“", '"').replace("”", '"')
    text = re.sub(r"```(?:json)?", "", text)
    text = text.replace("```", "")
    text = re.sub(r"//.*", "", text)

    start = None
    stack = []
    pairs = {"{": "}", "[": "]"}
    rev = {"}": "{", "]": "["}

    for i, ch in enumerate(text):
        if ch in pairs:
            if start is None:
                start = i
            stack.append(ch)
        elif ch in rev and stack and stack[-1] == rev[ch]:
            stack.pop()
            if not stack and start is not None:
                candidate = text[start:i + 1]
                try:
                    return json.loads(candidate)
                except Exception:
                    try:
                        return ast.literal_eval(candidate)
                    except Exception:
                        print(f"[{log_prefix}] ⚠️ JSON 抽取失败，片段前200字符:\n{candidate[:200]}")
                        return None

    print(f"[{log_prefix}] ⚠️ 未找到完整 JSON，原始输出前200字符:\n{text[:200]}")
    return None


# ======================================================
# JSON 输出修复器（仅修格式，不改语义）
# ======================================================
def _repair_json_with_llm(raw_text: str, log_prefix: str = "") -> Optional[Any]:
    REPAIR_PROMPT = f"""
你是一个 JSON 修复器。
下面内容包含一个“接近 JSON 但不合法”的结构。

请你：
1. 不改变原有语义
2. 不添加任何新信息
3. 仅将其修复为【合法 JSON】
4. 只输出 JSON，不要解释

原始内容：
{raw_text}
""".strip()

    try:
        resp, _ = call_llm(
            "qwen2-7b",
            [
                {"role": "system", "content": "你只输出 JSON"},
                {"role": "user", "content": REPAIR_PROMPT}
            ]
        )
        return _extract_and_parse_json(resp, f"{log_prefix}-REPAIR")
    except Exception as e:
        print(f"[{log_prefix}] ⚠️ JSON 修复失败: {e}")
        return None


# ======================================================
# STEP 1：情绪原子句拆解（低兜底率 · 语义优先版）
# ======================================================
def _rewrite_to_emotion_atoms(query: str) -> Dict[str, Any]:
    """
    情绪原子句拆解（工程增强版）

    核心原则：
    1. 不限制原子句数量（不截断）
    2. 允许非换行输出（逗号 / 顿号 / 分号 等）
    3. 只要能解析出 >=1 条情绪语义句，即“次优通过”
    4. 只有在完全无法拆解时，才启用规则兜底
    """

    PROMPT = f"""
你是一个情绪原子句拆解器。

你的任务是：
把用户输入拆解为若干条“情绪原子句”。

【强制规则】
1. 只输出拆解后的句子内容
2. 不要输出 JSON、序号、解释或说明
3. 每一句应表达一种情绪 / 感受 / 内心状态
4. 语言自然、简短、使用中文陈述句
5. 允许多句输出

【示例】

输入：
我知道这段关系已经结束了，但还是很难接受，也会感到遗憾，对未来有些迷茫。

输出：
难以接受一段关系已经结束
内心仍然感到遗憾
对未来的情感走向感到迷茫

【用户输入】
{query}
""".strip()

    def call_once(tag: str) -> Optional[List[str]]:
        print(f"[EMO-ATOM] 🔄 情绪原子句拆解（{tag}）")

        resp, _ = call_llm(
            "qwen2-7b",
            [
                {"role": "system", "content": "你只输出拆解后的句子文本"},
                {"role": "user", "content": PROMPT}
            ]
        )

        if not resp or not isinstance(resp, str):
            return None

        # --------------------------------------------------
        # 1️⃣ 清洗控制字符
        # --------------------------------------------------
        text = re.sub(r'[\x00-\x1f\x7f]', '', resp).strip()
        if not text:
            return None

        # --------------------------------------------------
        # 2️⃣ 统一“语义分隔符”
        #   - 若模型未使用换行，用标点做语义拆分
        # --------------------------------------------------
        if "\n" not in text:
            text = re.sub(r"[，,；;、]", "\n", text)

        # --------------------------------------------------
        # 3️⃣ 初步按行拆分
        # --------------------------------------------------
        raw_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        # --------------------------------------------------
        # 4️⃣ 清洗 & 语义过滤（不过度苛刻）
        # --------------------------------------------------
        atoms: List[str] = []
        for line in raw_lines:
            # 去掉可能的编号
            line = re.sub(r"^\s*[\-\*\d]+[\.、\)]\s*", "", line).strip()

            # 跳过明显非内容行
            if any(x in line for x in ("示例", "输入", "输出", "{", "}", "[", "]")):
                continue

            # 过短（几乎没语义）才丢
            if len(line) < 3:
                continue

            atoms.append(line)

        # --------------------------------------------------
        # 5️⃣ 次优通过策略
        #   - 只要有 1 条以上语义句，就认为成功
        # --------------------------------------------------
        if atoms:
            return atoms

        return None

    # ==================================================
    # 主流程
    # ==================================================
    atoms = call_once("首次")
    if atoms:
        return {"rewrite": atoms}

    atoms = call_once("重试")
    if atoms:
        return {"rewrite": atoms, "_retry": True}

    # ==================================================
    # 规则兜底（真正的最后防线）
    # ==================================================
    print("[EMO-ATOM] ⚠️ 启用规则兜底（标点拆句）")

    parts = re.split(r"[。！？!?；;，,\n]", query)
    atoms = [p.strip() for p in parts if p and len(p.strip()) > 2]

    return {
        "rewrite": atoms or [query.strip()],
        "_rule_fallback": True
    }

# ======================================================
# STEP 2：GoEmotions 标签标注（固定格式 · 非0降序输出版）
# ======================================================
def _goemotions_tagging_and_summary(query: str, atoms_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    新版 STEP2（工程稳定版）
    - LLM 只负责：句子 -> GoEmotions 标签（固定文本格式）
    - 程序负责：解析 / 校验 / 全量汇总 / sentiment/conflict 推断
    - 对外输出：goemotions_summary 仅保留非0并按count降序排列（STEP3拿到的也是这个）
    """

    # -----------------------------
    # 1) 取出情绪原子句
    # -----------------------------
    atoms = []
    if isinstance(atoms_json, dict):
        atoms = atoms_json.get("rewrite", [])
    if not isinstance(atoms, list) or not atoms:
        atoms = [query.strip()]

    atoms_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(atoms))

    # -----------------------------
    # 2) Prompt：固定输出格式
    # -----------------------------
    PROMPT = f"""
你是一个情绪标签标注器。

你的任务是：
为下面每一条“情绪原子句”选择 GoEmotions 标签。

【GoEmotions 标签集】
{", ".join(GOEMOTIONS_LABELS)}

【输出格式（必须严格遵守）】
每一行对应一个句子，格式为：
句子编号 | label1,label2

【强制规则】
1. 只输出标注结果，不要解释
2. 不要输出 JSON
3. 标签必须来自给定集合
4. 每句最多 3 个标签
5. 如果没有明显情绪，用 neutral

【情绪原子句列表】
{atoms_text}
""".strip()

    resp, _ = call_llm(
        "qwen2-7b",
        [
            {"role": "system", "content": "你只输出情绪标签标注结果"},
            {"role": "user", "content": PROMPT}
        ]
    )

    # -----------------------------
    # 3) 解析 LLM 输出
    # -----------------------------
    sentences: List[Dict[str, Any]] = []
    summary_full = {label: 0 for label in GOEMOTIONS_LABELS}

    if isinstance(resp, str):
        for line in resp.splitlines():
            if "|" not in line:
                continue

            left, right = line.split("|", 1)

            # 句子编号
            try:
                idx = int(left.strip()) - 1
            except ValueError:
                continue
            if idx < 0 or idx >= len(atoms):
                continue

            # 标签解析 & 校验
            labels = [l.strip() for l in right.split(",") if l.strip() in GOEMOTIONS_LABELS]
            if not labels:
                labels = ["neutral"]

            sentences.append({"text": atoms[idx], "labels": labels})

            for l in labels:
                summary_full[l] += 1

    # -----------------------------
    # 4) 程序侧推断 sentiment / conflict（用全量summary_full）
    # -----------------------------
    positive = (
        summary_full.get("joy", 0)
        + summary_full.get("love", 0)
        + summary_full.get("optimism", 0)
        + summary_full.get("gratitude", 0)
    )
    negative = (
        summary_full.get("sadness", 0)
        + summary_full.get("anger", 0)
        + summary_full.get("fear", 0)
        + summary_full.get("disgust", 0)
        + summary_full.get("remorse", 0)
    )

    if positive > negative:
        sentiment = "positive"
    elif negative > positive:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    has_conflict = positive > 0 and negative > 0

    # -----------------------------
    # 5) 对外输出：仅非0 + 降序排列（Ordered dict）
    # -----------------------------
    goemotions_summary = {
        k: v for k, v in sorted(
            summary_full.items(), key=lambda kv: kv[1], reverse=True
        )
        if v > 0
    }

    return {
        "goemotions_summary": goemotions_summary,  # ✅ 只非0，且按count降序
        "sentiment": sentiment,
        "has_conflict": has_conflict,
        "sentences": sentences
    }

## ======================================================
## STEP 3：多模型协商（A↔B 多轮 + C 仲裁）
## （固定 Plutchik 8 维，LLM 只输出分数）
## ======================================================
#def _negotiate_8d_vector(
#    query: str,
#    atoms_json: Dict[str, Any],
#    goemo_json: Dict[str, Any]
#) -> Tuple[str, bool]:
#    """
#    返回：
#    - vector_json_str: Plutchik 8 维情绪 JSON 数组字符串
#    - consensus: 是否由快系统达成一致
#    """
#
#    print("\n🧠 [STEP3 开始] 多模型协商输入：")
#    print("   原问题：", query)
#    print("   GoEmotions 标签（非0）：", goemo_json.get("goemotions_summary", {}))
#
#    # ===============================
#    # 固定 Plutchik 八维（绝对坐标系）
#    # ===============================
#    PLUTCHIK_8D = [
#        "joy",
#        "acceptance",
#        "fear",
#        "surprise",
#        "sadness",
#        "disgust",
#        "anger",
#        "anticipation"
#    ]
#
#    MAX_ROUNDS = 3
#    DELTA = 2.0  # 最大允许差异
#
#    BASE_CONTEXT = f"""
#用户原始输入：
#{query}
#
#GoEmotions 情绪标签统计（非0）：
#{json.dumps(goemo_json.get("goemotions_summary", {}), ensure_ascii=False)}
#""".strip()
#
#    # ===============================
#    # Prompt（不再要求 JSON）
#    # ===============================
#    PROMPT_SCORE = f"""
#你是情绪分析专家。
#
#请基于以下信息，对【Plutchik 八维情绪】分别给出 1–10 的强度评分。
#
#情绪维度顺序（非常重要）：
#1. joy
#2. acceptance
#3. fear
#4. surprise
#5. sadness
#6. disgust
#7. anger
#8. anticipation
#
#{BASE_CONTEXT}
#
#要求：
#- 只输出 8 个数字
#- 按顺序对应上述 8 个维度
#- 数字之间用空格或逗号分隔
#- 不要输出任何解释或文字
#""".strip()
#
#    # ===============================
#    # 工具函数
#    # ===============================
#    def _extract_scores(text: str) -> Optional[List[float]]:
#        if not text:
#            return None
#        nums = re.findall(r"\d+(?:\.\d+)?", text)
#        if len(nums) < 8:
#            return None
#        return [float(n) for n in nums[:8]]
#
#    def _call_scores(model: str, prompt: str, tag: str) -> Optional[List[float]]:
#        print(f"\n[{tag}] 💻 调用模型: {model}")
#        resp, _ = call_llm(
#            model,
#            [
#                {"role": "system", "content": "你只输出数字"},
#                {"role": "user", "content": prompt}
#            ]
#        )
#        scores = _extract_scores(resp)
#        if scores:
#            print(f"[{tag}] ✅ 得分结果: {scores}")
#        else:
#            print(f"[{tag}] ⚠️ 得分解析失败，原始输出前200字:\n{str(resp)[:200]}")
#        return scores
#
#    def _max_diff(a: List[float], b: List[float]) -> float:
#        return max(abs(x - y) for x, y in zip(a, b))
#
#    # ===============================
#    # 阶段一：A → B
#    # ===============================
#    last_A = None
#    last_B = None
#
#    for t in range(MAX_ROUNDS):
#        print(f"\n[EMO-NEGOTIATE] 🔄 阶段1 A→B 第 {t+1} 轮")
#
#        A = _call_scores("qwen2-1.5b", PROMPT_SCORE, "EMO-A")
#        if not A:
#            continue
#
#        B = _call_scores("qwen2-7b", PROMPT_SCORE, "EMO-B")
#        if not B:
#            continue
#
#        d = _max_diff(A, B)
#        print(f"[EMO-NEGOTIATE] 📏 A/B 最大差异 = {d:.2f}")
#
#        if d <= DELTA:
#            print("[EMO-NEGOTIATE] ✅ 快系统一致（阶段1）")
#            final = B
#            return json.dumps([
#                {"emotion": PLUTCHIK_8D[i], "score": final[i]}
#                for i in range(8)
#            ], ensure_ascii=False), True
#
#        last_A, last_B = A, B
#
#    # ===============================
#    # 阶段二：慢系统仲裁
#    # ===============================
#    print("\n[EMO-NEGOTIATE] ⚖️ 启动慢系统仲裁（deepseek-r1-7b）")
#
#    arb_prompt = PROMPT_SCORE + f"""
#
#快系统 A 评分：
#{last_A}
#
#快系统 B 评分：
#{last_B}
#
#请综合判断，给出最终 8 个分数（顺序不变）。
#"""
#
#    C = _call_scores("deepseek-r1-7b", arb_prompt, "EMO-C")
#
#    final = C or last_B or last_A or [5.0] * 8
#
#    print("\n[EMO-NEGOTIATE] 🧾 最终对齐结果：")
#    for i, name in enumerate(PLUTCHIK_8D):
#        print(f"   - {name}: {final[i]}/10")
#
#    return json.dumps([
#        {"emotion": PLUTCHIK_8D[i], "score": final[i]}
#        for i in range(8)
#    ], ensure_ascii=False), False
# ======================================================
# STEP 3：多模型协商（A↔B 多轮 + C 仲裁）
# （固定 Plutchik 8 维，LLM 只输出分数）
# ======================================================
#def _negotiate_8d_vector(
#    query: str,
#    atoms_json: Dict[str, Any],
#    goemo_json: Dict[str, Any]
#) -> Tuple[str, bool]:
#
#    print("\n🧠 [STEP3 开始] 多模型协商输入：")
#    print("   原问题：", query)
#    print("   GoEmotions 标签（非0）：", goemo_json.get("goemotions_summary", {}))
#
#    # ===============================
#    # 固定 Plutchik 八维
#    # ===============================
#    PLUTCHIK_8D = [
#        "joy",
#        "acceptance",
#        "fear",
#        "surprise",
#        "sadness",
#        "disgust",
#        "anger",
#        "anticipation"
#    ]
#
#    MAX_ROUNDS = 3
#    DELTA = 2.0
#
#    BASE_CONTEXT = f"""
#用户原始输入：
#{query}
#
#GoEmotions 情绪标签统计（非0）：
#{json.dumps(goemo_json.get("goemotions_summary", {}), ensure_ascii=False)}
#""".strip()
#
#    PROMPT_SCORE = f"""
#你是情绪分析专家。
#
#请基于以下信息，对【Plutchik 八维情绪】分别给出 1–10 的强度评分。
#
#情绪维度顺序（非常重要）：
#1. joy
#2. acceptance
#3. fear
#4. surprise
#5. sadness
#6. disgust
#7. anger
#8. anticipation
#
#{BASE_CONTEXT}
#
#要求：
#- 只输出 8 个数字
#- 按顺序对应上述 8 个维度
#- 数字之间用空格或逗号分隔
#- 不要输出任何解释或文字
#""".strip()
#
#    PROMPT_SCORE_ONLY = """
#下面有 8 个位置，请只输出 8 个 1–10 的数字。
#不要输出任何文字。
#示例：
#5 6 4 3 7 2 6 5
#""".strip()
#
#    # ===============================
#    # 工具函数
#    # ===============================
#    def _extract_scores(text: str) -> Optional[List[float]]:
#        if not text:
#            return None
#        nums = re.findall(r"\d+(?:\.\d+)?", text)
#        if len(nums) < 8:
#            return None
#        return [float(n) for n in nums[:8]]
#
#    def _call_scores(model: str, prompt: str, tag: str) -> Optional[List[float]]:
#        print(f"\n[{tag}] 💻 调用模型: {model}")
#
#        resp, _ = call_llm(
#            model,
#            [
#                {"role": "system", "content": "你只输出数字"},
#                {"role": "user", "content": prompt}
#            ]
#        )
#
#        scores = _extract_scores(resp)
#        if scores:
#            print(f"[{tag}] ✅ 得分结果: {scores}")
#            return scores
#
#        # 二次兜底：强制纯数字
#        print(f"[{tag}] ⚠️ 首次解析失败，触发纯数字补问")
#        print(f"[{tag}] 原始输出前200字:\n{str(resp)[:200]}")
#
#        resp2, _ = call_llm(
#            model,
#            [
#                {"role": "system", "content": "你只输出数字"},
#                {"role": "user", "content": PROMPT_SCORE_ONLY}
#            ]
#        )
#
#        scores2 = _extract_scores(resp2)
#        if scores2:
#            print(f"[{tag}] ✅ 补问成功: {scores2}")
#            return scores2
#
#        print(f"[{tag}] ❌ 二次仍失败")
#        return None
#
#    def _max_diff(a: List[float], b: List[float]) -> float:
#        return max(abs(x - y) for x, y in zip(a, b))
#
#    # ===============================
#    # 阶段一：快系统 A ↔ B
#    # ===============================
#    last_A = None
#    last_B = None
#
#    for t in range(MAX_ROUNDS):
#        print(f"\n[EMO-NEGOTIATE] 🔄 阶段1 A↔B 第 {t+1} 轮")
#
#        A = _call_scores("qwen2-1.5b", PROMPT_SCORE, "EMO-A")
#        if not A:
#            continue
#
#        B = _call_scores("qwen2-7b", PROMPT_SCORE, "EMO-B")
#        if not B:
#            continue
#
#        d = _max_diff(A, B)
#        print(f"[EMO-NEGOTIATE] 📏 A/B 最大差异 = {d:.2f}")
#
#        if d <= DELTA:
#            print("[EMO-NEGOTIATE] ✅ 快系统一致")
#            return json.dumps(
#                [{"emotion": PLUTCHIK_8D[i], "score": B[i]} for i in range(8)],
#                ensure_ascii=False
#            ), True
#
#        last_A, last_B = A, B
#
#    # ===============================
#    # 阶段二：慢系统仲裁
#    # ===============================
#    if last_A is None and last_B is None:
#        last_A = [5.0] * 8
#        last_B = [5.0] * 8
#
#    print("\n[EMO-NEGOTIATE] ⚖️ 启动慢系统仲裁（deepseek-r1-7b）")
#
#    arb_prompt = PROMPT_SCORE + f"""
#
#快系统 A 评分：
#{last_A}
#
#快系统 B 评分：
#{last_B}
#
#请综合判断，给出最终 8 个分数（顺序不变）。
#"""
#
#    C = _call_scores("deepseek-r1-7b", arb_prompt, "EMO-C")
#
#    final = C or last_B or last_A or [5.0] * 8
#
#    print("\n[EMO-NEGOTIATE] 🧾 最终对齐结果：")
#    for i, name in enumerate(PLUTCHIK_8D):
#        print(f"   - {name}: {final[i]}/10")
#
#    return json.dumps(
#        [{"emotion": PLUTCHIK_8D[i], "score": final[i]} for i in range(8)],
#        ensure_ascii=False
#    ), False
def _negotiate_8d_vector(
    query: str,
    atoms_json: Dict[str, Any],
    goemo_json: Dict[str, Any]
) -> Tuple[str, bool]:

    print("\n🧠 [STEP3 开始] B ↔ C 多轮协商")

    PLUTCHIK_8D = [
        "joy", "acceptance", "fear", "surprise",
        "sadness", "disgust", "anger", "anticipation"
    ]

    MAX_ROUNDS = 3
    DELTA = 2.0

    BASE_CONTEXT = f"""
用户原始输入：
{query}

GoEmotions 情绪标签统计（非0）：
{json.dumps(goemo_json.get("goemotions_summary", {}), ensure_ascii=False)}
""".strip()

    PROMPT_SCORE = f"""
你是情绪分析专家。

请基于以下信息，对【Plutchik 八维情绪】分别给出 1–10 的强度评分。

顺序：
1. joy
2. acceptance
3. fear
4. surprise
5. sadness
6. disgust
7. anger
8. anticipation

{BASE_CONTEXT}

要求：
- 只输出 8 个数字
- 不要解释
""".strip()

    PROMPT_REFINE = """
下面是上一轮模型给出的情绪评分结果：

{other_scores}

请你在充分参考上述结果的基础上，
结合原始文本，给出你认为更合理的 8 个情绪强度分数。

要求：
- 仍然只输出 8 个数字
- 顺序不变
""".strip()

    def extract_scores(text: str):
        nums = re.findall(r"\d+(?:\.\d+)?", text or "")
        return [float(n) for n in nums[:8]] if len(nums) >= 8 else None

    def call_scores(model, prompt):
        resp, _ = call_llm(
            model,
            [
                {"role": "system", "content": "你只输出数字"},
                {"role": "user", "content": prompt}
            ]
        )
        return extract_scores(resp)

    def is_consensus(B, C):
        diffs = [abs(b - c) for b, c in zip(B, C)]
        if max(diffs) <= DELTA:
            return True

        topB = sorted(range(8), key=lambda i: B[i], reverse=True)[:2]
        topC = sorted(range(8), key=lambda i: C[i], reverse=True)[:2]
        return bool(set(topB) & set(topC))

    # ===============================
    # 第 0 轮：B 首次给分
    # ===============================
    B = call_scores("qwen2-7b", PROMPT_SCORE)
    if not B:
        B = [5.0] * 8

    # ===============================
    # 多轮 BC 协商
    # ===============================
    for r in range(1, MAX_ROUNDS + 1):
        print(f"\n[EMO-NEGOTIATE] 🔄 协商轮次 {r}")

        # C 修正 B
        C = call_scores(
            "deepseek-r1-7b",
            PROMPT_REFINE.format(other_scores=B)
        )
        if not C:
            C = B

        if is_consensus(B, C):
            print("[EMO-NEGOTIATE] ✅ B/C 达成一致")
            final = C
            return json.dumps(
                [{"emotion": PLUTCHIK_8D[i], "score": final[i]} for i in range(8)],
                ensure_ascii=False
            ), True

        # B 再次向 C 靠拢
        B = call_scores(
            "qwen2-7b",
            PROMPT_REFINE.format(other_scores=C)
        ) or C

    # ===============================
    # 超出最大轮次：C 裁决
    # ===============================
    print("[EMO-NEGOTIATE] ⚖️ 达到最大轮次，使用 C 的结果")

    final = C or B or [5.0] * 8

    return json.dumps(
        [{"emotion": PLUTCHIK_8D[i], "score": final[i]} for i in range(8)],
        ensure_ascii=False
    ), False



#    # -----------------------------
#    # 最终兜底（保持工程可用）
#    # -----------------------------
#    fallback = last_B or last_A or [5.0] * 8
#    vector = [
#        {"emotion": e, "score": s}
#        for e, s in zip(EMOTIONS, fallback)
#    ]
#    return json.dumps(vector, ensure_ascii=False), False

# ======================================================
# 主入口（修复版：统一 atoms_list，防止后续被统计为 0）
# ======================================================
def run_emotion_analysis(query: str) -> Tuple[str, bool, Dict[str, Any]]:
    print("\n📊 [阶段1-3] 新版情绪识别开始（三步分析法）...")

    # ---------- STEP1 ----------
    atoms = _rewrite_to_emotion_atoms(query)

    print("\n✅ [STEP1 完成] 最终情绪原子句：")

    # ✅ 统一标准原子句列表（唯一可信源）
    atoms_list: List[str] = []
    if isinstance(atoms, dict):
        atoms_list = atoms.get("rewrite", [])
    if not isinstance(atoms_list, list) or not atoms_list:
        atoms_list = [query.strip()]

    for i, a in enumerate(atoms_list, 1):
        print(f"   [{i}] {a}")

    # ⚠️ 关键修复点：
    # 后续步骤一律使用 atoms_list，而不是 atoms dict

    # ---------- STEP2 ----------
    goemo = _goemotions_tagging_and_summary(
        query=query,
        atoms_json={
            "rewrite": atoms_list   # ✅ 显式、干净、可控
        }
    )

    # ---------- STEP3 ----------
    vector, consensus = _negotiate_8d_vector(
        query=query,
        atoms_json={
            "rewrite": atoms_list   # ✅ 保证 STEP3 不会看到空 atoms
        },
        goemo_json=goemo
    )

    # ---------- DEBUG INFO（不再被覆盖） ----------
    return vector, consensus, {
        "emotion_atoms": {
            "rewrite": atoms_list   # ✅ 永远是 List[str]
        },
        "goemotions": goemo,
        "consensus": consensus
    }
