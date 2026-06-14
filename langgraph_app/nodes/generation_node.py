from typing import List

from ..state import ConversationState

from ..services.llm_service import call_chat_model

from ..config import DEFAULT_AGENT_LLM

def generation_node(state: ConversationState) -> ConversationState:
    """
    文本生成节点（最终回复）：
    - 汇总：user_query + emotion + character_profile + 检索结果
    - 调用 LLM 生成最终回答
    - 🔧 修复：充分利用角色知识库信息，生成个性化的安慰回复
    """
    user_query = state.get("user_query", "")
    emotion_list = state.get("emotion_list") or []
    emotion_embedding = state.get("emotion_embedding") or []
    character_name = state.get("selected_character") or "支持者"
    character_profile = state.get("character_profile") or {}
    retrieved_memory: List[str] = state.get("retrieved_memory") or []
    
    # 🔧 获取角色的风格和支持策略信息
    character_style = state.get("character_style", "")
    support_strategy = state.get("support_strategy", "")
    
    # 🔧 获取对话历史（如果存在）
    conversation_history = state.get("conversation_history", [])
    if not conversation_history:
        conversation_history = state.get("messages", [])
    
    # 🔧 构建完整的角色信息（从character_profile中提取详细信息）
    role_info_parts = []
    
    # 1. 角色基本信息
    if character_name and character_name != "支持者":
        role_info_parts.append(f"角色名称：{character_name}")
    
    # 2. 从character_profile中提取详细信息
    if isinstance(character_profile, dict):
        # 提取关键信息
        for key, value in character_profile.items():
            if value and str(value).strip():
                # 跳过一些技术性字段
                if key not in ['context_embedding', 'embedding', 'id']:
                    role_info_parts.append(f"{key}：{value}")
    elif isinstance(character_profile, str):
        role_info_parts.append(character_profile)
    
    # 3. 添加角色风格信息
    if character_style:
        role_info_parts.append(f"\n【角色风格】\n{character_style}")
    
    # 4. 添加支持策略信息
    if support_strategy:
        role_info_parts.append(f"\n【支持策略】\n{support_strategy}")
    
    role_info_text = "\n".join(role_info_parts) if role_info_parts else f"角色：{character_name}"

    # 检索记忆文本
    memory_text = "\n\n".join(retrieved_memory) if retrieved_memory else "（暂无记忆内容）"

    # 情绪摘要文本
    if emotion_list:
        emo_lines = [f"{item.get('dim')}: {item.get('score')} - {item.get('analysis', '')}"
                     for item in emotion_list]
        emotion_summary = "\n".join(emo_lines)
    else:
        emotion_summary = f"情绪嵌入: {emotion_embedding}"

    # 🔧 改进的system_prompt，强调角色扮演和个性化
    system_prompt = f"""你正在扮演角色「{character_name}」。

你的任务：
1. **完全融入角色**：你不是一个通用的AI助手，而是「{character_name}」这个具体角色。你的说话方式、语气、用词都应该完全符合这个角色的设定。
2. **个性化安慰**：根据角色的性格特点、说话风格和支持策略，给出符合角色特点的安慰和建议。
3. **理解用户情绪**：仔细理解用户的情绪状态和具体问题，不要使用模板化的回复。
4. **对话连贯性**：如果用户指出你没有理解或重复了之前的内容，要诚恳道歉并重新理解。

重要原则：
- 不要使用通用的模板回复（如"我听到你说..."、"听起来这些经历..."等）
- 要用「{character_name}」这个角色特有的方式来表达
- 回复要真诚、具体、有针对性
- 字数控制在150字以内，但要充分表达共情和理解
"""

    # 🔧 构建包含对话历史的用户提示
    history_context = ""
    if conversation_history:
        history_lines = []
        for msg in conversation_history[-6:]:  # 只保留最近6轮对话
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                history_lines.append(f"来访者：{content}")
            elif role == "assistant":
                history_lines.append(f"你（{character_name}）：{content}")
        if history_lines:
            history_context = "\n\n【之前的对话】\n" + "\n".join(history_lines) + "\n"

    user_prompt = f"""
【来访者当前问题】
{user_query}
{history_context}

【你的角色信息】（请严格按照这个角色设定来回复）
{role_info_text}

【来访者的情绪状态】
{emotion_summary}

【相关记忆】（可以参考，但不要直接引用）
{memory_text}

请以「{character_name}」的身份和口吻，针对来访者的具体问题，给出真诚、个性化、有共情力的回复。

要求：
1. **不要使用模板**：不要使用"我听到你说..."、"听起来这些经历..."等模板化开头
2. **角色化表达**：用「{character_name}」这个角色特有的说话方式和语气
3. **针对性回复**：直接回应来访者的具体问题，不要回避或重复
4. **真诚共情**：表达对来访者情绪的理解，但要符合角色的表达方式
5. **简洁有力**：控制在150字以内，但要充分表达
"""

    # 🔧 构建包含对话历史的 messages
    messages = [{"role": "system", "content": system_prompt}]
    
    # 添加对话历史（转换为模型格式）
    for msg in conversation_history[-6:]:  # 只保留最近6轮
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role in ["user", "assistant"]:
            if role == "assistant":
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": "user", "content": content})
    
    # 添加当前用户问题
    messages.append({"role": "user", "content": user_prompt})

    # 🔧 添加错误处理和调试信息
    try:
        print(f"🔍 [generation_node] 调用模型: {DEFAULT_AGENT_LLM}")
        print(f"🔍 [generation_node] 用户问题: {user_query[:100]}...")
        print(f"🔍 [generation_node] 匹配角色: {character_name}")
        print(f"🔍 [generation_node] 角色信息长度: {len(role_info_text)} 字符")
        print(f"🔍 [generation_node] 情绪数量: {len(emotion_list)}")
        print(f"🔍 [generation_node] 记忆数量: {len(retrieved_memory)}")
        print(f"🔍 [generation_node] 对话历史轮数: {len(conversation_history)}")
        
        # 调用模型生成回答
        answer, raw = call_chat_model(DEFAULT_AGENT_LLM, messages)
        
        # 🔧 检查响应是否有效
        if not answer or len(answer.strip()) == 0:
            print(f"⚠️ [generation_node] 警告: 模型返回空响应")
            answer = "我刚才在思考你的这句话时好像遇到了一点小问题，但我依然在这里，愿意继续听你慢慢说。"
        elif len(answer.strip()) < 10:
            print(f"⚠️ [generation_node] 警告: 响应太短 ({len(answer)} 字符): {answer}")
            try:
                print(f"🔄 [generation_node] 尝试重新生成...")
                answer2, raw2 = call_chat_model(DEFAULT_AGENT_LLM, messages)
                if answer2 and len(answer2.strip()) > len(answer.strip()):
                    answer = answer2
                    raw = raw2
                    print(f"✅ [generation_node] 重新生成成功，新响应长度: {len(answer)}")
                else:
                    print(f"⚠️ [generation_node] 重新生成后响应仍然太短")
            except Exception as retry_error:
                print(f"❌ [generation_node] 重新生成失败: {retry_error}")
                if len(answer.strip()) < 5:
                    answer = "我刚才在思考你的这句话时好像遇到了一点小问题，但我依然在这里，愿意继续听你慢慢说。"
        
        print(f"✅ [generation_node] 生成成功，响应长度: {len(answer)} 字符")
        print(f"🔍 [generation_node] 响应预览: {answer[:200]}...")
        
        # 🔧 更新对话历史
        if "conversation_history" not in state:
            state["conversation_history"] = []
        
        state["conversation_history"].append({
            "role": "user",
            "content": user_query
        })
        state["conversation_history"].append({
            "role": "assistant",
            "content": answer
        })
        
        # 限制历史长度（保留最近10轮对话）
        if len(state["conversation_history"]) > 20:
            state["conversation_history"] = state["conversation_history"][-20:]
        
        # 存储最终答案和调试信息
        state["final_answer"] = answer
        state["generation_debug"] = {
            "model": DEFAULT_AGENT_LLM,
            "character_name": character_name,
            "response_length": len(answer) if answer else 0,
            "emotion_count": len(emotion_list),
            "memory_count": len(retrieved_memory),
            "history_count": len(conversation_history),
            "has_character_style": bool(character_style),
            "has_support_strategy": bool(support_strategy),
            "raw_response": raw,
            "error": None,
        }
        
    except Exception as e:
        print(f"❌ [generation_node] 生成失败: {str(e)}")
        import traceback
        print(f"❌ [generation_node] 完整错误堆栈:")
        traceback.print_exc()
        
        answer = "我刚才在思考你的这句话时好像遇到了一点小问题，但我依然在这里，愿意继续听你慢慢说。"
        
        state["final_answer"] = answer
        state["generation_debug"] = {
            "model": DEFAULT_AGENT_LLM,
            "character_name": character_name,
            "response_length": len(answer),
            "error": str(e),
            "error_type": type(e).__name__,
        }

    return state