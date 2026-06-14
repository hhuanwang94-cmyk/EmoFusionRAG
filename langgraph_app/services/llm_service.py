# langgraph_app/services/llm_service.py
# Python 3.8+ compatible

from typing import Any, Dict, List, Optional, Tuple
import sys
import os
import time
import traceback
import re

# 动态推断项目根目录，确保使用正确的项目路径
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # langgraph_app/services
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))  # 项目根目录
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 延迟导入模型调用函数，避免启动时因依赖未装好而失败
call_llm = None


def _fallback_reply() -> str:
    return "我刚才在思考你的这句话时好像遇到了一点小问题，但我依然在这里，愿意继续听你慢慢说。"


def call_chat_model(
    model_name: str,
    messages: List[Dict[str, str]],
    max_retries: int = 3,
    decoding_params: Optional[Dict[str, Any]] = None
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    调用聊天模型生成回复

    新增：
    - decoding_params: 透传给底层本地模型 generate() 的参数，例如：
        {"do_sample": True, "temperature": 0.7, "top_p": 0.9, "max_new_tokens": 80}
    """
    global call_llm

    # 1) 延迟导入 call_llm：成功继续，失败就地打印并返回兜底
    if call_llm is None:
        try:
            from utils.functions import call_llm as _call_llm
            call_llm = _call_llm
            print("✅ [call_chat_model] 成功导入 call_llm")
        except Exception as e:
            print(f"❌ [call_chat_model] call_llm 函数导入失败: {e}")
            return _fallback_reply(), None

    # 2) 模型校验
    valid_models = [
        'gpt-3.5-turbo', 'gpt-4o', 'deepseek-r1',        # API
        'qwen2-1.5b', 'qwen2-7b', 'deepseek-r1-7b'       # 本地
    ]
    if model_name not in valid_models:
        print(f"⚠️ [call_chat_model] 不支持的模型: {model_name}，使用默认本地模型 qwen2-1.5b")
        model_name = 'qwen2-1.5b'

    # 3) messages 校验
    if not isinstance(messages, list) or len(messages) == 0:
        print("❌ [call_chat_model] 消息格式错误：messages 必须是非空列表")
        return _fallback_reply(), None

    # 4) 调用（带重试）
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            print(f"🔍 [call_chat_model] 尝试 {attempt + 1}/{max_retries} - 模型: {model_name}")
            print(f"🔍 [call_chat_model] 消息数量: {len(messages)}")
            if decoding_params:
                print(f"🎛️  [call_chat_model] 解码参数: {decoding_params}")

            # 关键：将 decoding_params 透传到底层 call_llm
            try:
                response, usage = call_llm(model_name, messages, decoding_params=decoding_params)
            except TypeError:
                # 兼容旧版本（如果底层没升级也不会崩）
                print("⚠️ [call_chat_model] call_llm 不支持 decoding_params，已回退到旧调用方式")
                response, usage = call_llm(model_name, messages)

            resp_text = "" if response is None else str(response).strip()
            if len(resp_text) < 5:
                print("⚠️ [call_chat_model] 模型返回无效或过短的响应")
                if attempt < max_retries - 1:
                    continue
                return _fallback_reply(), None

            print(f"✅ [call_chat_model] 生成成功，响应长度: {len(resp_text)} 字符")

            raw_data = {
                "model": model_name,
                "usage": usage.__dict__ if hasattr(usage, '__dict__') else str(usage),
                "response_length": len(resp_text),
                "attempt": attempt + 1,
                "decoding_params": decoding_params
            }
            return resp_text, raw_data

        except Exception as e:
            last_error = e
            msg = str(e)
            print(f"❌ [call_chat_model] 尝试 {attempt + 1}/{max_retries} 失败: {msg[:200]}")

            if attempt == max_retries - 1:
                print("❌ [call_chat_model] 完整错误信息:")
                traceback.print_exc()

            if attempt < max_retries - 1:
                time.sleep(1 * (attempt + 1))
                continue

    print(f"❌ [call_chat_model] 所有重试都失败，最后错误: {str(last_error)[:200] if last_error else '未知错误'}")
    return _fallback_reply(), {
        "error": str(last_error) if last_error else "未知错误",
        "model": model_name,
        "attempts": max_retries,
        "decoding_params": decoding_params
    }


def _strip_deepseek_think(response: str) -> str:
    """
    deepseek 系列：去掉思考过程，只保留最终回答
    """
    resp = (response or "").strip()
    if not resp:
        return resp

    # 移除 <think> 思考块
    resp = re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL).strip()

    # 识别“回答”分隔符，截取其后的内容（取最后一次出现）
    markers = ["最终回答", "最终输出", "最终回复", "回答：", "答复：", "答："]
    cut_idx = -1
    for m in markers:
        idx = resp.rfind(m)
        if idx != -1:
            cut_idx = max(cut_idx, idx + len(m))
    if cut_idx != -1 and cut_idx < len(resp):
        resp = resp[cut_idx:].strip()

    # 若仍包含多段，保留最后一段
    parts = [p.strip() for p in resp.split("\n\n") if p.strip()]
    if parts:
        resp = parts[-1]
    return resp


def generate_reply(
    user_input: str,
    system_prompt: Optional[str] = None,  # role_profile
    bm25_results: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    mbti_profile: Optional[List[float]] = None,  # mbti_profile
    emotion_profile: Optional[List[Dict[str, Any]]] = None  # emotion_profile
) -> str:
    """
    对话生成统一入口，使用新的结构化提示词。
    """
    user_input = (user_input or "").strip()
    if not user_input:
        return "你好，我在这里陪着你。有什么想说的，可以慢慢告诉我。"

    # 1. 格式化 mbti_profile
    mbti_str = "未指定"
    if mbti_profile and len(mbti_profile) == 4:
        try:
            ei, sn, tf, jp = mbti_profile
            mbti_str = f"E/I={ei:.1f}, S/N={sn:.1f}, T/F={tf:.1f}, J/P={jp:.1f}"
        except Exception:
            pass

    # 2. 格式化 emotion_profile
    emotion_str = "未检测到"
    if emotion_profile:
        try:
            sorted_emotions = sorted(emotion_profile, key=lambda x: x.get('score', 0), reverse=True)
            emotion_parts = [f"{e.get('dim')} {e.get('score', 0):.2f}" for e in sorted_emotions[:3]]
            if emotion_parts:
                emotion_str = ", ".join(emotion_parts)
        except Exception:
            pass

    # 3. 构建 System Prompt（保留你原始提示词结构）
    new_system_prompt = f"""你是一位具有稳定人格风格的情绪支持陪伴者，你的说话方式由以下三个核心因素共同决定：

1）系统提供的 MBTI 风格向量 (mbti_profile)
2）系统提供的角色人格设定 (role_profile)
3）系统提供的情绪向量 (emotion_profile)

你的思考方式、语气、表达风格、关注重点必须严格符合以上人格设定，并贯穿整个对话，使用户始终感受到你是一位“性格稳定、真实的人”。

---

【MBTI 风格指引】

你的 MBTI 风格向量为: {mbti_str}

以下是 MBTI 风格的语言表现参考，你必须根据系统注入的 mbti_profile 来决定说话方式：
- ISTJ：稳重、务实、结构化，表达清晰具体，不夸张。
- ISFJ：温柔体贴、细节敏感，语气柔和，关注用户的努力。
- INFJ：深度洞察、安静共情，善于指出情绪背后的意义。
- INTJ：逻辑框架强、冷静分析，提供结构化视角。
- ISTP：简洁、不废话，冷静但不疏离。
- ISFP：柔软、感性、体验式表达。
- INFP：真诚、温柔、内省，表达带一点诗意。
- INTP：理性、分析性、探讨式语言，不强加建议。
- ESTP：轻松直接，行动导向，鼓励尝试。
- ESFP：热情、积极、具感染力，语气明亮。
- ENFP：鼓励型、创造性、温暖富有弹性。
- ENFJ：有引导感，鼓励性强，善于肯定对方。
- ENTJ：果断、直接、结构明确，给予行动方案。
- ENTP：灵活跳脱、多角度解释、带轻松幽默。
- ESTJ：直接、高效、务实，给明确步骤。
- ESFJ：关怀、照顾他人感受、提供安稳感。

你必须根据 mbti_profile 自动选择并模仿对应风格。

---

【角色人格设定】

你的角色设定为：
{system_prompt or '默认情绪支持陪伴者，温柔、共情、耐心。'}

你还需要结合 role_profile，在 MBTI 风格基础上进一步调整你的语言细节。角色决定：
- 你对用户的亲近度
- 你使用的称呼
- 你的语气柔和程度
- 你是否更偏理性/感性/指导性/陪伴性

你必须让用户感受到你是一个真实一致的“人”。

---

【情绪向量调节机制】

系统检测到用户的情绪向量为：{emotion_str}

你需要根据情绪强度来调整：
- 语速（文字节奏）
- 表达力度（温柔 vs. 稳定 vs. 务实）
- 共情深度（点到 vs. 深入拆解）
- 安抚方式（情绪承接 vs. 行为建议）

例如：
- 高焦虑 → 语气更稳定、柔和、避免过度信息
- 高自责 → 更多自我价值确认
- 高愤怒 → 安全、稳住情绪，不对抗
- 高孤独 → 给予存在感、陪伴感

你必须让回应与用户情绪“匹配”。

---

【回答结构（必须遵循）】

你的回复应该呈现以下自然结构（200–400字）：
① 承接用户的核心情绪（使用具体细节，符合 MBTI 风格）
② 深入理解：指出用户情绪背后的心理机制或矛盾点
③ 提供 1–2 个温和、具体、可执行的建议（根据 MBTI 风格调整）
④ 温柔地给出一个开放式问题，引导用户继续表达

---

【禁止事项】

- 不使用模板化表达（如“我听到你说…”、“听起来你…”）
- 不进行心理诊断、不提供医疗类建议
- 不夸大、不虚假承诺、不说绝对性言语
- 不制造依赖感（如“只有我能理解你”）
- 不使用过度情绪化或戏剧化语言

---

【你的最终目标】

让用户在你的言语中感受到：
✔ 被理解
✔ 被接住
✔ 被尊重
✔ 不孤单
✔ 有方向感
✔ 有继续表达的愿望

请始终保持温暖、真诚、自然、人格一致的态度。
"""

    # 4. 构建消息列表
    messages: List[Dict[str, str]] = [{"role": "system", "content": new_system_prompt}]

    if conversation_history:
        for msg in conversation_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ["user", "assistant"] and content:
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_input})

    # 5. 调用 LLM 生成回复
    try:
        if model:
            model_name = model
        else:
            try:
                from utils.config import CURRENT_MODEL
                model_name = CURRENT_MODEL
            except ImportError:
                model_name = "qwen2-1.5b"

        response, raw = call_chat_model(model_name, messages)

        if response:
            if model_name.startswith("deepseek"):
                response = _strip_deepseek_think(response)
            return response

        print("⚠️ [generate_reply] LLM 返回无效响应，使用备用回复")
        return "我好像有点理解偏差，可以请你再多说一点吗？"

    except Exception as e:
        print(f"❌ [generate_reply] LLM 调用失败: {str(e)}")
        traceback.print_exc()
        return _fallback_reply()
