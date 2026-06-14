# langgraph_app/nodes/strategy_node.py
"""
多轮对话策略规划节点

根据对话历史和情绪状态，规划当前轮次应采用的支持策略。
"""

from typing import Dict, Any
from ..state import ConversationState
from ..services.strategy_service import (
    plan_strategy,
    generate_strategy_prompt,
    StrategyPlan
)


def strategy_node(state: ConversationState) -> ConversationState:
    """
    策略规划节点：
    - 根据对话历史和情绪状态规划当前轮次的对话策略
    - 输出策略规划结果和策略提示词
    
    Args:
        state: 对话状态
    
    Returns:
        更新后的对话状态，包含策略规划信息
    """
    print("\n🎯 [策略规划] 开始规划多轮对话策略...")
    
    # 获取必要信息
    user_query = state.get("user_query", "")
    conversation_history = state.get("conversation_history", [])
    emotion_embedding = state.get("emotion_embedding", None)
    emotion_label = state.get("emotion_label", None)
    
    # 如果没有情绪信息，尝试从 emotion_list 中获取
    if not emotion_label:
        emotion_list = state.get("emotion_list", [])
        if emotion_list and isinstance(emotion_list, list) and len(emotion_list) > 0:
            # 取第一个情绪作为主导情绪
            first_emotion = emotion_list[0]
            if isinstance(first_emotion, dict):
                emotion_label = first_emotion.get("dim", None)
    
    try:
        # 规划策略
        strategy_plan = plan_strategy(
            conversation_history=conversation_history,
            emotion_embedding=emotion_embedding,
            emotion_label=emotion_label,
            user_input=user_query
        )
        
        # 生成策略提示词
        strategy_prompt = generate_strategy_prompt(strategy_plan)
        
        # 保存到状态
        state["strategy_plan"] = {
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
        state["strategy_prompt"] = strategy_prompt
        
        # 打印策略信息
        print(f"   📍 当前轮次: 第{strategy_plan.current_round}轮")
        print(f"   📍 当前阶段: {strategy_plan.current_phase}")
        print(f"   📍 阶段目标: {strategy_plan.phase_goal}")
        print(f"   📍 主要策略: {strategy_plan.primary_strategy}")
        if strategy_plan.secondary_strategy:
            print(f"   📍 辅助策略: {strategy_plan.secondary_strategy}")
        print(f"   📍 策略理由: {strategy_plan.reasoning}")
        
        # 添加到调试信息
        if "debug_info" not in state:
            state["debug_info"] = {}
        state["debug_info"]["strategy_plan"] = state["strategy_plan"]
        
    except Exception as e:
        print(f"   ⚠️ 策略规划失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 使用默认策略
        state["strategy_plan"] = {
            "current_round": 1,
            "current_phase": "倾听共情",
            "primary_strategy": "Reflection of Feelings",
            "secondary_strategy": "Restatement or Paraphrasing",
            "phase_goal": "让用户感到被理解和接纳",
            "reasoning": "使用默认策略"
        }
        state["strategy_prompt"] = """
【多轮对话策略指导】
- 当前阶段：倾听共情
- 主要策略：情感反映（识别并反馈用户的情绪）
- 策略提示：首先认真倾听，用自己的话复述用户的感受，让用户知道你理解他/她。
"""
    
    print("   ✅ 策略规划完成")
    return state
