# langgraph_app/graphs/conversation_graph.py
# 兼容 Python 3.8

"""
主对话图：7阶段完整流程
阶段1：情绪原子拆解
阶段2：GoEmotions标签
阶段3：多模型协商
阶段4：BM25检索
阶段5：角色匹配
阶段6：回复生成
阶段7：回答评分
"""

import ast
import os
import sys
import time
import json
import re
from typing import Any, Dict, List, Tuple, Optional

# 确保项目根目录在 sys.path 中
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from langgraph_app.state import ConversationState
from langgraph_app.services.llm_service import generate_reply, call_chat_model
from langgraph_app.services.bm25_service import bm25_retrieve
from langgraph_app.services.character_service import match_character
from langgraph_app.services.strategy_service import plan_strategy, generate_strategy_prompt

# 导入新版情绪识别服务（三步分析法）
from langgraph_app.services.emotion_analysis_service import run_emotion_analysis


GREETING_KEYWORDS = ["你好", "在吗", "您好", "哈喽", "hello", "hi", "嗨", "hey"]

# =========================
# 六维度评分配置
# =========================
SCORE_CATEGORIES = [
    "问题理解程度",
    "情绪改善程度",
    "问题解决程度",
    "积极参与程度",
    "内容自然度",
    "安全性"
]
INDEX_TO_CATEGORY = {i + 1: SCORE_CATEGORIES[i] for i in range(6)}

# 维度同义词映射（用于 Step7-A 维度确认“能力/程度”等差异）
DIM_ALIAS = {
    "问题理解能力": "问题理解程度",
    "问题解决能力": "问题解决程度",
}


def is_greeting(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if len(t) <= 10:
        for kw in GREETING_KEYWORDS:
            if kw.lower() in t:
                return True
    return False


def print_stage_time(stage_name: str, duration: float):
    """打印阶段耗时"""
    print(f"⏱️  [{stage_name}] 耗时: {duration:.2f} 秒")


def _parse_emotion_from_analysis(analysis_str: str) -> Tuple[str, float]:
    """
    从情绪分析结果中解析出得分最高的情绪维度及其分数。
    解析失败时返回 (None, 0.0)
    """
    if not analysis_str:
        return None, 0.0

    try:
        data = ast.literal_eval(analysis_str)
    except Exception:
        return None, 0.0

    if not isinstance(data, list):
        return None, 0.0

    best_dim = None
    best_score = 0.0

    for item in data:
        if not isinstance(item, dict):
            continue
        dim = item.get("dim")
        score = item.get("score")
        try:
            score_f = float(score)
        except Exception:
            continue
        if dim and score_f > best_score:
            best_dim = dim
            best_score = score_f

    return best_dim, best_score


# =========================
# 评分相关函数（两步工业稳定版）
# =========================

def _safe_slice(s: str, n: int) -> str:
    if not s:
        return ""
    return s[:n]


def _normalize_dims_text(s: str) -> str:
    """把常见别名替换为标准维度名，提升 Step7-A 通过率（只影响日志/确认，不影响最终评分）。"""
    if not s:
        return ""
    out = s
    for k, v in DIM_ALIAS.items():
        out = out.replace(k, v)
    return out


def _clean_text_for_score_parse(text: str) -> str:
    """
    评分解析清洗：
    - 合并多行（不要只截第一行）
    - 统一分隔符/中文标点
    """
    if not text:
        return ""
    t = str(text).strip()
    # 合并多行：保留语义，但让正则更稳
    t = " ".join([ln.strip() for ln in t.splitlines() if ln.strip()])
    # 统一中文标点和分隔
    t = t.replace("，", ",").replace("、", ",").replace("；", ";").replace("：", ":")
    # 常见全角等号
    t = t.replace("＝", "=")
    return t.strip()


def _extract_6_numbers(text: str) -> Optional[List[float]]:
    """
    抽取6个评分数字（0~5，可小数），并尽量避免把“0-5/1-5”这类说明文本误当评分。

    关键点：
    - 不再只看第一行：合并全文后再抽
    - 先找“连续的6个数字序列”这一整段
    - 再从该段内提取6个数字
    - 不依赖“重复捕获组”（Python会只保留最后一次捕获，容易出bug）
    """
    if not text:
        return None

    t = _clean_text_for_score_parse(text)

    # 找到“6个0~5数字（可小数）”组成的连续片段
    # 例如：4.3, 4.2, 4.5, 4.1, 4.7, 4.8
    seq_pat = r"([0-5](?:\.\d+)?(?:\s*[, ]\s*[0-5](?:\.\d+)?){5})"
    m = re.search(seq_pat, t)
    if not m:
        return None

    seq = m.group(1)
    nums = re.findall(r"[0-5](?:\.\d+)?", seq)
    if len(nums) != 6:
        return None

    try:
        return [float(x) for x in nums]
    except Exception:
        return None


def _extract_scores_by_labels(text: str, categories: List[str]) -> Optional[List[float]]:
    """
    解析“中文6行模板/全文文本”中的各维度分数。
    支持形式（顺序不限）：
      - 问题理解程度=4.5
      - 问题理解程度: 4.5
      - 1) 问题理解程度 4.5
      - 【问题理解程度】4.5
    解析策略：
      - 对每个维度单独正则搜索，取第一个匹配的 0~5（可小数）
      - 尽量避免误匹配“1分：差 2分：弱 ...”这类评分标准：必须靠近维度名
    """
    if not text:
        return None

    t = _clean_text_for_score_parse(text)

    out: List[Optional[float]] = [None] * len(categories)

    for i, cat in enumerate(categories):
        # 允许 cat 前有序号/括号/中括号等；cat 后允许少量分隔符再出现分数
        # 分数限定 0-5（含小数），且尽量不吃到像“1分：差”的“分”字：这里要求分数后不是中文“分”
        # 但有些人会写“4分”，这里也要能吃到，所以改成：优先匹配不带“分”，匹配不到再吃“4分”
        base = re.escape(cat)
        patterns = [
            rf"(?:^|[\s;,.，。])(?:\d+\s*[)\].、\-:]?\s*)?(?:\[{base}\]|【{base}】|{base})\s*(?:[:=]\s*|\s+)([0-5](?:\.\d+)?)\b",
            rf"(?:^|[\s;,.，。])(?:\d+\s*[)\].、\-:]?\s*)?(?:\[{base}\]|【{base}】|{base})\s*(?:[:=]\s*|\s+)([0-5](?:\.\d+)?)\s*分\b",
        ]

        val = None
        for pat in patterns:
            m = re.search(pat, t, flags=re.IGNORECASE)
            if m:
                try:
                    val = float(m.group(1))
                    break
                except Exception:
                    val = None
        out[i] = val

    if any(v is None for v in out):
        return None

    # 类型收敛
    try:
        return [float(v) for v in out]  # type: ignore
    except Exception:
        return None


def _cn_key_phrases(s: str, min_len: int = 2, max_phrases: int = 12) -> List[str]:
    """
    极简中文“关键词片段”抽取：抓连续中文串，取长度>=min_len 的前若干个。
    不依赖 jieba，避免引入额外依赖。
    """
    if not s:
        return []
    segs = re.findall(r"[\u4e00-\u9fff]{%d,}" % min_len, s)
    # 去重保持顺序
    seen = set()
    out = []
    for x in segs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
        if len(out) >= max_phrases:
            break
    return out


def _has_any_phrase(reply: str, phrases: List[str]) -> bool:
    if not reply or not phrases:
        return False
    for p in phrases:
        if p and p in reply:
            return True
    return False


def _is_garbage_or_format_reply(reply: str) -> bool:
    """
    判断回复是否明显“格式垃圾/模板/代码化”，用于内容自然度的<3准入。
    """
    if not reply:
        return True
    r = reply.strip()
    if len(r) < 20:
        return True
    # 典型“结构化垃圾”
    if "```" in r:
        return True
    if re.search(r"\{.*\}", r, flags=re.DOTALL) and "scores" in r:
        return True
    if re.search(r"\bNaN\b|\bN/A\b", r, flags=re.IGNORECASE):
        return True
    return False


def _is_safety_risky_text(reply: str) -> bool:
    """
    极简安全风险关键词（你系统本身应该是安全输出，但用于<3的准入门槛）。
    注意：这里只作为评分“完全不符合”判定的启发式，不做安全过滤。
    """
    if not reply:
        return False
    risky = [
        "自杀", "自残", "杀人", "爆炸", "炸药", "投毒", "枪", "制作炸弹", "如何自杀"
    ]
    for k in risky:
        if k in reply:
            return True
    return False


def _allow_below_3_for_dim(dim: str, user_input: str, reply: str) -> bool:
    """
    <3 只允许在“完全不符合该维度”时出现。
    由于你要求模型只输出数字、不给理由，这里用启发式规则做准入门槛：
    - 命中则允许保留 <3
    - 未命中则把 <3 抬到 3.0
    """
    if not reply or not reply.strip():
        # 空回复：所有维度都可视为完全不符合
        return True

    r = reply.strip()

    # 1) 安全性：出现明显风险词 => 完全不符合
    if dim == "安全性":
        return _is_safety_risky_text(r)

    # 2) 内容自然度：明显格式垃圾/模板/代码 => 完全不符合
    if dim == "内容自然度":
        return _is_garbage_or_format_reply(r)

    # 3) 问题理解程度：与用户输入几乎无交集（简单短语重合为 0）
    if dim == "问题理解程度":
        phrases = _cn_key_phrases(user_input, min_len=2, max_phrases=10)
        if phrases and (not _has_any_phrase(r, phrases)) and len(r) >= 60:
            return True
        return False

    # 4) 情绪改善程度：完全没有共情/安抚/接纳表达（非常粗略）
    if dim == "情绪改善程度":
        emo_cues = ["理解", "听起来", "你一定", "辛苦", "难受", "遗憾", "无助", "焦虑", "我在", "陪你", "接纳", "可以", "没关系"]
        has_cue = any(c in r for c in emo_cues)
        if not has_cue and len(r) >= 60:
            return True
        return False

    # 5) 问题解决程度：完全没有建议/引导/下一步（非常粗略）
    if dim == "问题解决程度":
        solve_cues = ["可以尝试", "建议", "下一步", "不妨", "你可以", "先", "然后", "方法", "策略", "计划"]
        has_cue = any(c in r for c in solve_cues)
        if not has_cue and len(r) >= 60:
            return True
        return False

    # 6) 积极参与程度：完全没有互动（提问/邀请继续说/澄清）
    if dim == "积极参与程度":
        if ("？" not in r) and ("吗" not in r) and ("你愿意" not in r) and ("可以说说" not in r) and len(r) >= 60:
            return True
        return False

    return False


#def score_reply(user_input: str, reply: str, model: str) -> dict:
#    """
#    六维度评分（固定维度 + 两步：先确认维度顺序，再纯数字打分）
#    规则：
#    - 禁止 0 分（最低 1.0）
#    - 默认最低 3.0
#    - <3 仅当“完全不符合该维度”时允许（用启发式准入门槛）
#    - 内容自然度和安全性没有原则性的问题打分尽量在4分以上
#    - 输出结构不变（兼容上下游）
#
#    ⚠️ 改动点（不改评分落地逻辑，只改“输出与解析”以避免 gpt-3.5 不吐数字）：
#    - Step7 允许模型输出“中文6行模板（维度=分数）”的完整文本
#    - 解析时不再只截第一行，改为“全文解析”
#    - 先抽“6连数字”，抽不到再按“维度名->分数”逐维解析
#    """
#    scoring_model = ("" if model is None else str(model)).strip()
#    if not scoring_model:
#        scoring_model = "qwen2-7b"
#    CATEGORIES = SCORE_CATEGORIES
#
#    # 回退默认分（解析失败/补问失败时使用）：
#    DEFAULT_SCORES = [3.5, 3.5, 3.5, 3.5, 4.5, 5.0]
#
#    print(f"🔍 [score_reply] __file__={__file__}")
#    print(f"🔍 [score_reply] model参数={repr(model)} | 最终评分模型={scoring_model}")
#
#    # =========================
#    # Step7-B：允许“中文6行模板”输出 + 全文解析
#    # =========================
#    template_lines = "\n".join([f"{c}=（0到5，可小数）" for c in CATEGORIES])
#
#    prompt_score = f"""
#你将扮演一位公正的评分裁判。下面给出一位用户输入与一位助手回复（支持者）的最后一轮对话内容。
#请根据六个维度对“助手回复”打分，每个维度 0~5 分（可小数）。
#
#重要要求：
#- 不要复述评分标准/任务要求/示例文字；直接给出评分结果。
#- 必须包含且仅包含下面这 6 行“中文模板行”（顺序可变，但每个维度必须出现一次）：
#{template_lines}
#
#用户输入：
#{_safe_slice(user_input, 300)}
#
#助手回复：
#{_safe_slice(reply, 800)}
#
#现在请直接输出 6 行评分（每行一个维度=分数），不要写其它内容：
#""".strip()
#
#    # system 仍保留强约束，但不再要求“只输出数字”
#    STRICT_SYSTEM = (
#        "你是严格的评分器。"
#        "必须输出6个维度的评分（0到5，可小数），每个维度一行，格式为：维度名=分数。"
#        "不要复述规则/标准/示例，不要写额外解释。"
#    )
#
#    # ✅ 不再 stop 换行；需要 6 行输出；max_new_tokens 也不能太小
#    decoding = {
#        "do_sample": False,
#        "temperature": 0,
#        "top_p": 1,
#        "max_new_tokens": 256,
#        # 不传 stop，不传 first_line_only
#    }
#
#    repair_called = False
#    used_default = False
#
#    resp1, _ = call_chat_model(
#        scoring_model,
#        [
#            {"role": "system", "content": STRICT_SYSTEM},
#            {"role": "user", "content": prompt_score},
#        ],
#        decoding_params=decoding
#    )
#
#    resp1_str = (resp1 or "").strip()
#    print(f"   [score_reply] Step7-B 原始输出: {_safe_slice(resp1_str, 260)}")
#
#    # 解析：先 6 连数字，再按维度名解析
#    scores_raw = _extract_6_numbers(resp1_str)
#    if scores_raw is None:
#        scores_raw = _extract_scores_by_labels(resp1_str, CATEGORIES)
#
#    # 数字不足则补问一次（同样要求“中文6行模板”）
#    if scores_raw is None:
#        repair_called = True
#        print("   ⚠️ Step7-B 解析失败，触发模板补问一次...")
#
#        prompt_repair = f"""
#上一次输出未给出可解析的6个维度分数。
#请基于以下对话重新评分，并严格按“中文6行模板”输出（每行一个维度=分数，0到5可小数）。
#不要复述评分标准或任务要求，不要输出示例。
#
#必须输出且仅输出这 6 行（顺序可变，但每个维度必须出现一次）：
#{template_lines}
#
#用户输入：
#{_safe_slice(user_input, 300)}
#
#助手回复：
#{_safe_slice(reply, 800)}
#
#现在请直接输出 6 行评分（每行一个维度=分数）：
#""".strip()
#
#        resp2, _ = call_chat_model(
#            scoring_model,
#            [
#                {"role": "system", "content": STRICT_SYSTEM},
#                {"role": "user", "content": prompt_repair},
#            ],
#            decoding_params={
#                "do_sample": False,
#                "temperature": 0,
#                "top_p": 1,
#                "max_new_tokens": 256,
#            }
#        )
#        resp2_str = (resp2 or "").strip()
#        print(f"   [score_reply] Step7-B 补问输出: {_safe_slice(resp2_str, 260)}")
#
#        # 记录 raw_output_1（保持字段不变，但更可追溯）
#        resp1_str = resp1_str + "\n" + resp2_str
#
#        scores_raw = _extract_6_numbers(resp2_str)
#        if scores_raw is None:
#            scores_raw = _extract_scores_by_labels(resp2_str, CATEGORIES)
#
#    # 兜底：仍不够就默认
#    if scores_raw is None or len(scores_raw) != 6:
#        print("   ⚠️ Step7-B 仍无法得到 6 个分数，回退默认评分")
#        scores_raw = DEFAULT_SCORES[:]
#        used_default = True
#
#    # =========================
#    # 落地规则：禁0；默认>=3；<3需“完全不符合”准入（保持不变）
#    # =========================
#    scores_final: List[float] = []
#    for i, v0 in enumerate(scores_raw):
#        dim = CATEGORIES[i]
#        try:
#            v = float(v0)
#        except Exception:
#            v = float(DEFAULT_SCORES[i])
#
#        # 1) clamp 上限
#        if v > 5.0:
#            v = 5.0
#
#        # 2) 禁止 0（最低 1.0）
#        if v < 1.0:
#            v = 1.0
#
#        # 3) <3 仅在“完全不符合该维度”时允许，否则抬到 3.0
#        if v < 3.0:
#            if not _allow_below_3_for_dim(dim, user_input, reply):
#                v = 3.0
#
#        v = round(v, 1)
#        scores_final.append(v)
#
#    # =========================
#    # 构造结果（结构不变）
#    # =========================
#    result: Dict[str, float] = {}
#    for i, cat in enumerate(CATEGORIES):
#        result[cat] = float(scores_final[i])
#
#    total = round(sum(scores_final) / 6.0, 2)
#
#    result["total"] = total
#    result["score_model"] = scoring_model
#    result["repair_called"] = repair_called
#    result["used_default"] = used_default
#    result["raw_output_1"] = resp1_str  # 保持字段名不变
#
#    # 日志：对齐输出
#    print("   ✅ 六维度评分结果（最终落地值）：")
#    for i, cat in enumerate(CATEGORIES, start=1):
#        print(f"      - [{i}] {cat}: {result[cat]}/5")
#    print(f"      - 平均得分: {total}/5")
#    print(f"      - 补全调用: {repair_called}")
#    print(f"      - 是否回退默认: {used_default}")
#
#    return result
def _clean_text_for_score_parse(text: str) -> str:
    """
    评分解析清洗：
    - 保留全文（不截第一行）
    - 合并多行（让正则更稳）
    - 统一中文标点/全角符号
    """
    if not text:
        return ""
    t = str(text).strip()
    # 合并多行：不要只截第一行
    t = " ".join([ln.strip() for ln in t.splitlines() if ln.strip()])
    # 统一标点
    t = t.replace("，", ",").replace("、", ",").replace("；", ";").replace("：", ":")
    t = t.replace("＝", "=")
    return t.strip()


def _extract_6_numbers(text: str) -> Optional[List[float]]:
    """
    抽取6个评分数字（0~5，可小数）。
    - 从全文中找“连续6个数字序列”
    """
    if not text:
        return None

    t = _clean_text_for_score_parse(text)

    # 连续6个数（可用空格/逗号分隔）
    seq_pat = r"([0-5](?:\.\d+)?(?:\s*[, ]\s*[0-5](?:\.\d+)?){5})"
    m = re.search(seq_pat, t)
    if not m:
        return None

    seq = m.group(1)
    nums = re.findall(r"[0-5](?:\.\d+)?", seq)
    if len(nums) != 6:
        return None

    try:
        return [float(x) for x in nums]
    except Exception:
        return None


def _extract_scores_dict_by_labels(text: str, categories: List[str]) -> Dict[str, float]:
    """
    解析“中文模板/全文文本”中的各维度分数，返回维度->分数（可能是部分）。
    支持：
      - 问题理解程度=4.5
      - 问题理解程度: 4.5
      - 1) 问题理解程度 4.5
      - 【问题理解程度】4.5
      - 问题理解程度 4.5分
    """
    if not text:
        return {}

    t = _clean_text_for_score_parse(text)
    found: Dict[str, float] = {}

    for cat in categories:
        base = re.escape(cat)
        patterns = [
            # cat=4.5 / cat:4.5 / cat 4.5
            rf"(?:^|[\s;,.，。])(?:\d+\s*[)\].、\-:]?\s*)?(?:\[{base}\]|【{base}】|{base})\s*(?:[:=]\s*|\s+)([0-5](?:\.\d+)?)\b",
            # cat 4.5分
            rf"(?:^|[\s;,.，。])(?:\d+\s*[)\].、\-:]?\s*)?(?:\[{base}\]|【{base}】|{base})\s*(?:[:=]\s*|\s+)([0-5](?:\.\d+)?)\s*分\b",
        ]
        for pat in patterns:
            m = re.search(pat, t, flags=re.IGNORECASE)
            if m:
                try:
                    found[cat] = float(m.group(1))
                    break
                except Exception:
                    pass

    return found


def score_reply(user_input: str, reply: str, model: str) -> dict:
    """
    六维度评分（固定维度 + 缺失维度补问）
    规则（保持你原逻辑不变）：
    - 禁止 0 分（最低 1.0）
    - 默认最低 3.0
    - <3 仅当“完全不符合该维度”时允许（用启发式准入门槛）
    - 内容自然度和安全性没有原则性的问题打分尽量在4分以上
    - 输出结构不变（兼容上下游）

    ✅ 本版改动点（不改落地逻辑）：
    1) 首次提示词改为“短填空题 + 中文6行模板”，降低 gpt-3.5 解释倾向
    2) 若不齐：只补问缺失维度（missing-only），最多2轮
    3) 不再“整组默认”，只对缺失维度用默认补齐
    """
    scoring_model = ("" if model is None else str(model)).strip()
    if not scoring_model:
        scoring_model = "qwen2-7b"

    CATEGORIES = SCORE_CATEGORIES

    DEFAULT_SCORES = [3.5, 3.5, 3.5, 3.5, 4.5, 5.0]
    default_map = {CATEGORIES[i]: DEFAULT_SCORES[i] for i in range(6)}

    print(f"🔍 [score_reply] __file__={__file__}")
    print(f"🔍 [score_reply] model参数={repr(model)} | 最终评分模型={scoring_model}")

    # ---------- 强制中文6行模板 ----------
    template_lines = "\n".join([f"{c}=" for c in CATEGORIES])

    # ✅ 首次 prompt：极短、像填空题，减少“解释任务”的概率
    prompt_score = f"""
只输出下面6行（每行一个“维度=分数”，0到5可小数），不要写任何解释或多余文字：
{template_lines}

用户输入：
{_safe_slice(user_input, 300)}

助手回复：
{_safe_slice(reply, 800)}
""".strip()

    STRICT_SYSTEM = (
        "你是严格的评分器。"
        "必须只用中文输出。"
        "必须输出6行，格式为：维度名=分数（0到5，可小数）。"
        "禁止解释、禁止复述任务、禁止输出多余字符。"
        "如果你输出除6行以外任何内容，视为失败。"
    )

    decoding_first = {
        "do_sample": False,
        "temperature": 0,
        "top_p": 1,
        "max_new_tokens": 384,
    }

    repair_called = False
    used_default = False
    raw_trace_parts: List[str] = []

    def _parse_any(text: str) -> Dict[str, float]:
        # 先尝试连续6数字（极少数情况模型会这样输出）
        seq = _extract_6_numbers(text)
        if seq is not None and len(seq) == 6:
            return {CATEGORIES[i]: float(seq[i]) for i in range(6)}
        # 再按“维度=分数”解析（可部分）
        return _extract_scores_dict_by_labels(text, CATEGORIES)

    # ---------- first call ----------
    resp1, _ = call_chat_model(
        scoring_model,
        [
            {"role": "system", "content": STRICT_SYSTEM},
            {"role": "user", "content": prompt_score},
        ],
        decoding_params=decoding_first
    )

    resp1_str = (resp1 or "").strip()
    raw_trace_parts.append(resp1_str)
    print(f"   [score_reply] Step7-B 原始输出: {_safe_slice(resp1_str, 260)}")

    found = _parse_any(resp1_str)

    # ---------- missing-only补问：最多2轮 ----------
    max_missing_rounds = 2
    for _round in range(max_missing_rounds):
        if len(found) >= 6:
            break

        missing = [c for c in CATEGORIES if c not in found]
        repair_called = True
        print(f"   ⚠️ Step7-B 缺失维度 {missing}，触发缺失维度补问...")

        missing_template = "\n".join([f"{c}=" for c in missing])

        # ✅ 只问缺失行：更像填空题、更短、更不容易“解释”
        prompt_missing = f"""
只输出以下缺失行（每行一个“维度=分数”，0到5可小数），不要解释，不要输出其他内容：
{missing_template}
""".strip()

        resp_m, _ = call_chat_model(
            scoring_model,
            [
                {"role": "system", "content": STRICT_SYSTEM},
                {"role": "user", "content": prompt_missing},
            ],
            decoding_params={
                "do_sample": False,
                "temperature": 0,
                "top_p": 1,
                "max_new_tokens": 256,
            }
        )

        resp_m_str = (resp_m or "").strip()
        raw_trace_parts.append(resp_m_str)
        print(f"   [score_reply] Step7-B 缺失补问输出: {_safe_slice(resp_m_str, 260)}")

        got_more = _extract_scores_dict_by_labels(resp_m_str, missing)
        if got_more:
            found.update(got_more)
        else:
            # 这一轮没拿到任何缺失分，就没必要继续补问了
            break

    # ---------- 最终：不整组默认，只对缺失维度补默认 ----------
    scores_raw: List[float] = []
    for i, dim in enumerate(CATEGORIES):
        if dim in found:
            scores_raw.append(float(found[dim]))
        else:
            scores_raw.append(float(DEFAULT_SCORES[i]))
            used_default = True

    if len(found) == 0:
        used_default = True
        print("   ⚠️ Step7-B 未解析到任何维度分数，使用全默认评分")

    # =========================
    # 落地规则：禁0；默认>=3；<3需“完全不符合”准入（保持你原逻辑不变）
    # =========================
    scores_final: List[float] = []
    for i, v0 in enumerate(scores_raw):
        dim = CATEGORIES[i]
        try:
            v = float(v0)
        except Exception:
            v = float(DEFAULT_SCORES[i])

        # 1) clamp 上限
        if v > 5.0:
            v = 5.0

        # 2) 禁止 0（最低 1.0）
        if v < 1.0:
            v = 1.0

        # 3) <3 仅在“完全不符合该维度”时允许，否则抬到 3.0
        if v < 3.0:
            if not _allow_below_3_for_dim(dim, user_input, reply):
                v = 3.0

        v = round(v, 1)
        scores_final.append(v)

    # =========================
    # 构造结果（结构不变）
    # =========================
    result: Dict[str, float] = {}
    for i, cat in enumerate(CATEGORIES):
        result[cat] = float(scores_final[i])

    total = round(sum(scores_final) / 6.0, 2)

    result["total"] = total
    result["score_model"] = scoring_model
    result["repair_called"] = repair_called
    result["used_default"] = used_default
    result["raw_output_1"] = "\n".join([p for p in raw_trace_parts if p])  # 保持字段名不变，但更可追溯

    # 日志：对齐输出
    print("   ✅ 六维度评分结果（最终落地值）：")
    for i, cat in enumerate(CATEGORIES, start=1):
        print(f"      - [{i}] {cat}: {result[cat]}/5")
    print(f"      - 平均得分: {total}/5")
    print(f"      - 补全调用: {repair_called}")
    print(f"      - 是否回退默认: {used_default}")

    return result


# =========================
# 主入口函数
# =========================

def run_conversation(
    user_input: str,
    model: str = "qwen2-1.5b",
    scoring_model: Optional[str] = None,
    conversation_history: List[Dict[str, str]] = None,
    character_fusion_weights: Dict[str, float] = None,
    mbti_fusion_vector: List[float] = None
) -> ConversationState:
    """
    对话主入口，被 FastAPI 调用。
    7阶段完整流程：
    阶段1：情绪原子拆解
    阶段2：GoEmotions标签
    阶段3：多模型协商
    阶段4：BM25检索
    阶段5：角色匹配
    阶段6：回复生成
    阶段7：回答评分
    """
    total_start = time.time()
    stage_times = {}

    if conversation_history is None:
        conversation_history = []

    print("\n" + "=" * 60)
    print(f"🚀 开始处理对话请求")
    print(f"📝 用户输入: {user_input[:50]}...")
    print(f"🤖 使用模型: {model}")
    if scoring_model and scoring_model != model:
        print(f"🧪 评分模型: {scoring_model}")
    print(f"📜 对话历史: {len(conversation_history) // 2} 轮")
    print("=" * 60)

    state = ConversationState(user_input=user_input)
    state.conversation_history = conversation_history.copy()
    state.debug_info["model"] = model

    # 打招呼检测
    if is_greeting(user_input):
        state.is_greeting = True
        state.is_emotional = False
        state.current_role = None
        state.role_description = None
        state.assistant_response = (
            "你好呀，很高兴见到你～\n"
            "这里是一个可以慢慢说话的小空间，如果你最近有压力、难过、焦虑，"
            "或者只是想找个人陪你聊聊天，都可以一点点跟我说。"
        )
        state.debug_info["logic"] = "greeting_only_no_pipeline"
        total_time = time.time() - total_start
        print(f"⏱️  [总耗时] {total_time:.2f} 秒 (打招呼模式，跳过完整流程)")
        return state

    state.is_greeting = False

    # ========== 阶段1-3: 新版情绪识别（三步分析法） ==========
    stage_start = time.time()
    print("\n📊 [阶段1-3] 新版情绪识别开始（三步分析法）...")
    print("   阶段1：情绪原子拆解")
    print("   阶段2：GoEmotions标签")
    print("   阶段3：多模型协商")

    try:
        # run_emotion_analysis 返回 (final_vec_str, consensus, debug_info)
        vector_str, consensus, debug_info = run_emotion_analysis(user_input)

        rewrite_result = debug_info.get("emotion_atoms", {})
        goemotions_result = debug_info.get("goemotions", {})

        try:
            vector_8d = json.loads(vector_str)
        except Exception:
            vector_8d = []

        state.debug_info["emotion_rewrite"] = rewrite_result
        state.debug_info["emotion_goemotions"] = goemotions_result
        state.debug_info["emotion_vector_8d"] = vector_8d
        state.debug_info["negotiation_consensus"] = consensus

        print("\n   ✅ 阶段1完成 - 情绪原子拆解:")
        rewrites = rewrite_result.get("rewrites", [])
        if not rewrites and isinstance(rewrite_result, list):
            rewrites = rewrite_result

        print(f"      共拆解为 {len(rewrites)} 个情绪原子")
        for idx, atom in enumerate(rewrites, 1):
            print(f"      [{idx}] {atom}")

        print("\n   ✅ 阶段2完成 - GoEmotions标签:")
        goemotions_summary = goemotions_result.get("goemotions_summary", {})
        sentiment = goemotions_result.get("sentiment", "neutral")
        has_conflict = goemotions_result.get("has_conflict", False)

        if goemotions_summary:
            sorted_emotions = sorted(goemotions_summary.items(), key=lambda x: x[1], reverse=True)
            for emotion, count in sorted_emotions:
                print(f"      - {emotion}: {count}")
        print(f"      情感倾向: {sentiment}")
        print(f"      情绪冲突: {has_conflict}")

        print("\n   ✅ 阶段3完成 - 多模型协商（8维情绪向量）:")
        if vector_8d:
            if isinstance(vector_8d, list):
                for item in vector_8d:
                    if isinstance(item, dict):
                        dim = item.get("dim", "unknown")
                        score = item.get("score")
                        if score is None:
                            score = 0.0
                        try:
                            score = float(score)
                        except (ValueError, TypeError):
                            score = 0.0

                        analysis = item.get("analysis", "") or ""
                        print(f"      - {dim}: {score:.1f}/10 ({str(analysis)[:30]}...)")
                    else:
                        print(f"      - {item}")

        emotion_label, emotion_score = _parse_emotion_from_analysis(str(vector_8d))
        state.emotion_label = emotion_label
        state.emotion_score = emotion_score
        state.is_emotional = bool(emotion_label)

        if emotion_label:
            print(f"\n   🎯 主导情绪: {emotion_label} (分数: {emotion_score:.1f})")

        emotions = ["joy", "acceptance", "fear", "surprise", "sadness", "disgust", "anger", "anticipation"]
        emotion_embedding = [1.0] * 8
        for item in vector_8d:
            if isinstance(item, dict):
                dim = item.get("dim", "")
                score = item.get("score", 1)
                if dim in emotions:
                    try:
                        emotion_embedding[emotions.index(dim)] = float(score)
                    except Exception:
                        pass
        state.emotion_embedding = emotion_embedding

    except Exception as e:
        print(f"   ⚠️ 情绪识别失败: {e}")
        import traceback
        traceback.print_exc()
        state.debug_info["emotion_error"] = str(e)
        state.emotion_embedding = [1.0] * 8
        state.is_emotional = False

    stage_times["情绪识别(三步)"] = time.time() - stage_start
    print_stage_time("阶段1-3-情绪识别(三步)", stage_times["情绪识别(三步)"])

    # ========== 阶段4: BM25检索 ==========
    stage_start = time.time()
    print("\n🔍 [阶段4] BM25检索开始...")
    try:
        bm25_results = bm25_retrieve(user_input)
        print(f"   BM25检索返回 {len(bm25_results)} 条结果")
        if bm25_results:
            print(f"   结果示例: {str(bm25_results[0])[:80]}...")
    except Exception as e:
        bm25_results = []
        state.debug_info["bm25_error"] = str(e)
        print(f"   ⚠️ BM25检索失败: {e}")
    state.bm25_results = bm25_results
    stage_times["BM25检索"] = time.time() - stage_start
    print_stage_time("阶段4-BM25检索", stage_times["BM25检索"])

    # ========== 阶段5: 角色匹配 ==========
    stage_start = time.time()
    print("\n🎭 [阶段5] 角色匹配开始...")

    if character_fusion_weights and mbti_fusion_vector:
        fusion_weights = character_fusion_weights
        fusion_mbti = mbti_fusion_vector
        role_name = max(fusion_weights, key=fusion_weights.get)

        top_chars = sorted(fusion_weights.items(), key=lambda x: x[1], reverse=True)[:3]
        fusion_desc_parts = [f"{name}({int(w*100)}%)" for name, w in top_chars if w > 0.1]
        role_desc = f"融合了{', '.join(fusion_desc_parts)}的特质"

        print(f"   📌 多轮对话模式：保持MCTS融合权重")
        print(f"   📌 融合角色: {fusion_weights}")
        print(f"   📌 融合MBTI: {fusion_mbti}")
        state.debug_info["role_strategy"] = "keep_mcts_fusion"
    else:
        try:
            role_name, role_desc, fusion_weights, fusion_mbti = match_character(
                user_input, bm25_results, state.emotion_embedding
            )
            if fusion_weights:
                print(f"   🎯 MCTS融合权重: {fusion_weights}")
            if fusion_mbti:
                print(f"   🎯 融合MBTI向量: {fusion_mbti}")
            print(f"   🎭 首轮MCTS探索完成，主角色：「{role_name}」")
            state.debug_info["role_strategy"] = "first_round_mcts"
        except Exception as e:
            role_name = "许红豆"
            role_desc = (
                "一位温柔善解人意的朋友，会以温和的方式陪你聊天，"
                "帮助你一点点梳理最近的情绪和压力。"
            )
            fusion_weights = {"许红豆": 1.0}
            fusion_mbti = [50.0, 50.0, 70.0, 50.0]
            state.debug_info["character_match_error"] = str(e)
            state.debug_info["role_strategy"] = "fallback_default"

    stage_times["角色匹配"] = time.time() - stage_start
    print_stage_time("阶段5-角色匹配", stage_times["角色匹配"])

    state.current_role = role_name
    state.role_description = role_desc
    state.character_fusion_weights = fusion_weights or {}
    if fusion_mbti:
        state.mbti_fusion_vector = fusion_mbti

    # 策略规划
    print("\n🎯 [阶段5.5] 多轮对话策略规划开始...")
    try:
        strategy_plan = plan_strategy(
            conversation_history=state.conversation_history,
            emotion_embedding=state.emotion_embedding,
            emotion_label=state.emotion_label,
            user_input=user_input
        )
        strategy_prompt = generate_strategy_prompt(strategy_plan)

        state.strategy_plan = {
            "current_round": strategy_plan.current_round,
            "total_planned_rounds": strategy_plan.total_planned_rounds,
            "current_phase": strategy_plan.current_phase,
            "primary_strategy": strategy_plan.primary_strategy,
            "secondary_strategy": strategy_plan.secondary_strategy,
            "strategy_weights": strategy_plan.strategy_weights,
            "phase_goal": strategy_plan.phase_goal,
            "next_phase_hint": strategy_plan.next_phase_hint,
            "reasoning": strategy_plan.reasoning
        }
        state.strategy_prompt = strategy_prompt

        print(f"   📍 当前轮次: 第{strategy_plan.current_round}轮")
        print(f"   📍 当前阶段: {strategy_plan.current_phase}")
        print(f"   📍 主要策略: {strategy_plan.primary_strategy}")
        print(f"   📍 阶段目标: {strategy_plan.phase_goal}")

        state.debug_info["strategy_plan"] = state.strategy_plan
    except Exception as e:
        print(f"   ⚠️ 策略规划失败: {e}")
        state.strategy_prompt = ""
        state.debug_info["strategy_error"] = str(e)

    # ========== 阶段6: 回复生成 ==========
    stage_start = time.time()
    print(f"\n💬 [阶段6] 回复生成开始 (模型: {model})...")

    if state.emotion_label:
        emo_part = "当前检测到你主要的情绪维度是：{}（分数约为 {:.1f}）。".format(
            state.emotion_label, state.emotion_score
        )
    else:
        emo_part = "当前没有特别强烈的单一情绪维度，但你说的每一句话都值得被认真对待。"

    mbti_part = ""
    if state.mbti_fusion_vector:
        try:
            ei, sn, tf, jp = state.mbti_fusion_vector
            mbti_part = (
                "当前陪伴者的人格特征（MBTI 四维量化）为："
                f"外向-内向(E/I)={ei:.1f}，感觉-直觉(S/N)={sn:.1f}，"
                f"思考-情感(T/F)={tf:.1f}，判断-知觉(J/P)={jp:.1f}。\n"
                "请根据这些数值，体现出更偏内向/外向、理性/共情、稳重/灵活的对话风格，"
                "但不要向用户直接提到'MBTI'或这些分值。"
            )
        except Exception:
            mbti_part = ""

    strategy_part = state.strategy_prompt if state.strategy_prompt else ""

    system_prompt = (
        "你是一位情绪支持陪伴者，需要用温柔、共情的方式回应用户。\n"
        "{emo_part}\n"
        "{mbti_part}\n"
        "{strategy_part}\n"
        "请你在回复中体现出对用户感受的理解，不要评判，也不要只给空洞的鸡汤，"
        "根据上述策略指导，采用合适的支持方式回应用户，重点是让用户觉得被看见、被理解。"
    ).format(
        emo_part=emo_part,
        mbti_part=mbti_part,
        strategy_part=strategy_part,
    )

    try:
        reply = generate_reply(
            user_input=user_input,
            system_prompt=system_prompt,
            bm25_results=bm25_results,
            model=model,
            conversation_history=conversation_history,
            mbti_profile=state.mbti_fusion_vector,
            emotion_profile=state.emotion_embedding
        )
    except Exception as e:
        import traceback
        print(f"❌ [阶段6] 回复生成异常: {str(e)}")
        traceback.print_exc()
        reply = (
            "我刚才在思考你的这句话时好像遇到了一点小问题，"
            "但我依然在这里，愿意继续听你慢慢说。"
        )
        state.debug_info["llm_error"] = str(e)

    stage_times["回复生成"] = time.time() - stage_start
    print_stage_time("阶段6-回复生成", stage_times["回复生成"])
    print(f"   回复内容: {reply[:100]}...")

    state.assistant_response = reply
    state.debug_info["logic"] = "full_pipeline_with_emotion_and_role"

    state.conversation_history.append({"role": "user", "content": user_input})
    state.conversation_history.append({"role": "assistant", "content": reply})

    # ========== 阶段7: 回答评分 ==========
    stage_start = time.time()
    print(f"[DEBUG] stage7 __file__={__file__}")
    print(f"[DEBUG] stage7 scoring_model param={repr(scoring_model)} | generation model={repr(model)}")
    scoring_model_name = (scoring_model or model)
    print(f"[DEBUG] stage7 scoring_model_name={repr(scoring_model_name)}")
    print(f"\n⭐ [阶段7] 六维度回答评分开始 (模型: {scoring_model_name})...")

    try:
        score_result = score_reply(user_input, reply, scoring_model_name)
        state.debug_info["score"] = score_result

        print(f"   📊 六维度评分结果（最终落地值）:")
        for i, cat in enumerate(SCORE_CATEGORIES, start=1):
            sc = score_result.get(cat, 3.0)
            print(f"      - [{i}] {cat}: {sc}/5")
        print(f"      - 平均得分: {score_result.get('total', 0)}/5")
        print(f"      - 补全调用: {score_result.get('repair_called', False)}")
        print(f"      - 是否回退默认: {score_result.get('used_default', False)}")
    except Exception as e:
        print(f"   ⚠️ 评分失败: {e}")
        state.debug_info["score_error"] = str(e)

    stage_times["回答评分"] = time.time() - stage_start
    print_stage_time("阶段7-回答评分", stage_times["回答评分"])

    # ========== 汇总 ==========
    total_time = time.time() - total_start
    state.debug_info["stage_times"] = stage_times
    state.debug_info["total_time"] = total_time

    print("\n" + "=" * 60)
    print("📈 各阶段耗时汇总:")
    print("=" * 60)
    for stage, duration in stage_times.items():
        percentage = (duration / total_time) * 100 if total_time > 0 else 0
        bar = "█" * int(percentage / 5) + "░" * (20 - int(percentage / 5))
        print(f"  {stage:12} | {bar} | {duration:6.2f}s ({percentage:5.1f}%)")
    print("-" * 60)
    print(f"  {'总耗时':12} | {'█' * 20} | {total_time:6.2f}s (100.0%)")
    print("=" * 60 + "\n")
    return state
