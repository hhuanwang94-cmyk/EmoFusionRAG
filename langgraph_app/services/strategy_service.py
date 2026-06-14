# langgraph_app/services/strategy_service.py
"""
多轮对话策略规划服务

根据用户情绪状态和对话历史，规划当前轮次应采用的支持策略。
支持7种心理支持策略的动态选择和组合。
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json


class SupportStrategy(Enum):
    """7种心理支持策略"""
    REFLECTION = "Reflection of Feelings"      # 情感反映：识别并反馈用户情绪
    AFFIRMATION = "Affirmation and Reassurance" # 肯定安抚：肯定价值，提供鼓励
    SELF_DISCLOSURE = "Self-disclosure"         # 自我表露：分享经历建立信任
    SUGGESTION = "Providing Suggestions"        # 提供建议：给出建设性建议
    INFORMATION = "Information"                 # 提供信息：提供事实和资源
    RESTATEMENT = "Restatement or Paraphrasing" # 复述确认：重复确认理解
    QUESTION = "Question"                       # 提问引导：引导表达和思考


@dataclass
class StrategyPlan:
    """策略规划结果"""
    current_round: int = 1                      # 当前对话轮次
    total_planned_rounds: int = 4               # 规划的总轮次
    current_phase: str = "倾听共情"              # 当前阶段名称
    primary_strategy: str = "Reflection of Feelings"  # 主策略
    secondary_strategy: Optional[str] = None    # 辅助策略
    strategy_weights: Dict[str, float] = field(default_factory=dict)  # 各策略权重
    phase_goal: str = ""                        # 当前阶段目标
    next_phase_hint: str = ""                   # 下一阶段提示
    reasoning: str = ""                         # 策略选择理由


# 对话阶段定义
CONVERSATION_PHASES = {
    1: {
        "name": "倾听共情",
        "goal": "让用户感到被理解和接纳，建立信任关系",
        "primary": SupportStrategy.REFLECTION,
        "secondary": SupportStrategy.RESTATEMENT,
        "prompt_hint": "首先认真倾听，用自己的话复述用户的感受，让用户知道你理解他/她。"
    },
    2: {
        "name": "深入了解",
        "goal": "通过提问深入了解用户的具体情况和需求",
        "primary": SupportStrategy.QUESTION,
        "secondary": SupportStrategy.REFLECTION,
        "prompt_hint": "通过温和的开放式提问，引导用户说出更多细节，同时继续表达理解。"
    },
    3: {
        "name": "肯定鼓励",
        "goal": "肯定用户的价值和努力，增强其信心",
        "primary": SupportStrategy.AFFIRMATION,
        "secondary": SupportStrategy.SELF_DISCLOSURE,
        "prompt_hint": "肯定用户已经做出的努力，可以适当分享类似经历，让用户感到不孤单。"
    },
    4: {
        "name": "建议支持",
        "goal": "在充分理解的基础上，提供具体可行的建议",
        "primary": SupportStrategy.SUGGESTION,
        "secondary": SupportStrategy.INFORMATION,
        "prompt_hint": "基于前面的了解，提供1-2个具体、温和、可操作的建议，而非空洞的鸡汤。"
    }
}


# 情绪-策略适配规则
EMOTION_STRATEGY_RULES = {
    "sadness": {
        "preferred": [SupportStrategy.REFLECTION, SupportStrategy.AFFIRMATION],
        "avoid": [SupportStrategy.SUGGESTION],  # 悲伤时不急于给建议
        "note": "悲伤时需要更多倾听和陪伴，不要急于解决问题"
    },
    "anger": {
        "preferred": [SupportStrategy.REFLECTION, SupportStrategy.RESTATEMENT],
        "avoid": [SupportStrategy.SUGGESTION],  # 愤怒时不要急于给建议
        "note": "愤怒时先让用户发泄，确认理解其感受"
    },
    "fear": {
        "preferred": [SupportStrategy.AFFIRMATION, SupportStrategy.INFORMATION],
        "avoid": [],
        "note": "恐惧时需要安抚和提供确定性信息"
    },
    "joy": {
        "preferred": [SupportStrategy.AFFIRMATION, SupportStrategy.QUESTION],
        "avoid": [],
        "note": "积极情绪时可以多互动，深入了解"
    },
    "disgust": {
        "preferred": [SupportStrategy.REFLECTION, SupportStrategy.QUESTION],
        "avoid": [SupportStrategy.SELF_DISCLOSURE],
        "note": "厌恶情绪时需要理解其原因"
    },
    "surprise": {
        "preferred": [SupportStrategy.QUESTION, SupportStrategy.INFORMATION],
        "avoid": [],
        "note": "惊讶时帮助用户理清思路"
    },
    "anticipation": {
        "preferred": [SupportStrategy.SUGGESTION, SupportStrategy.AFFIRMATION],
        "avoid": [],
        "note": "期待时可以帮助规划和鼓励"
    },
    "acceptance": {
        "preferred": [SupportStrategy.AFFIRMATION, SupportStrategy.SUGGESTION],
        "avoid": [],
        "note": "接受状态时可以进一步推进"
    }
}


def calculate_conversation_round(conversation_history: List[Dict]) -> int:
    """
    计算当前对话轮次
    
    Args:
        conversation_history: 对话历史列表，每个元素包含 role 和 content
    
    Returns:
        当前轮次（从1开始）
    """
    if not conversation_history:
        return 1
    
    # 统计用户发言次数作为轮次
    user_turns = sum(1 for msg in conversation_history if msg.get("role") == "user")
    return user_turns + 1  # 当前是新的一轮


def get_dominant_emotion(emotion_embedding: Optional[List[float]]) -> Tuple[str, float]:
    """
    从8维情绪向量中获取主导情绪
    
    Args:
        emotion_embedding: 8维情绪向量 [joy, acceptance, fear, surprise, sadness, disgust, anger, anticipation]
    
    Returns:
        (主导情绪名称, 情绪强度)
    """
    if not emotion_embedding or len(emotion_embedding) < 8:
        return ("neutral", 0.0)
    
    emotions = ["joy", "acceptance", "fear", "surprise", "sadness", "disgust", "anger", "anticipation"]
    max_idx = 0
    max_score = emotion_embedding[0]
    
    for i, score in enumerate(emotion_embedding):
        if score > max_score:
            max_score = score
            max_idx = i
    
    return (emotions[max_idx], max_score)


def adjust_phase_by_emotion(
    base_phase: int,
    dominant_emotion: str,
    emotion_intensity: float,
    conversation_history: List[Dict]
) -> int:
    """
    根据情绪状态调整对话阶段
    
    Args:
        base_phase: 基于轮次的基础阶段
        dominant_emotion: 主导情绪
        emotion_intensity: 情绪强度
        conversation_history: 对话历史
    
    Returns:
        调整后的阶段
    """
    # 高强度负面情绪时，延长倾听阶段
    negative_emotions = ["sadness", "anger", "fear", "disgust"]
    
    if dominant_emotion in negative_emotions and emotion_intensity > 6.0:
        # 强烈负面情绪，保持在倾听共情阶段
        if base_phase > 2:
            return 2  # 最多到深入了解阶段
    
    # 如果用户情绪已经好转（从对话历史判断），可以加速进入建议阶段
    if len(conversation_history) >= 4:
        recent_emotions = []
        # 这里可以从历史中提取情绪变化趋势
        # 简化处理：如果轮次够多且情绪不是强烈负面，允许进入建议阶段
        if dominant_emotion in ["joy", "acceptance", "anticipation"]:
            return min(base_phase + 1, 4)
    
    return base_phase


def plan_strategy(
    conversation_history: Optional[List[Dict]] = None,
    emotion_embedding: Optional[List[float]] = None,
    emotion_label: Optional[str] = None,
    user_input: str = ""
) -> StrategyPlan:
    """
    规划当前轮次的对话策略
    
    Args:
        conversation_history: 对话历史
        emotion_embedding: 8维情绪向量
        emotion_label: 情绪标签
        user_input: 当前用户输入
    
    Returns:
        StrategyPlan 策略规划结果
    """
    conversation_history = conversation_history or []
    
    # 1. 计算当前轮次
    current_round = calculate_conversation_round(conversation_history)
    
    # 2. 获取主导情绪
    if emotion_label:
        dominant_emotion = emotion_label.lower()
        emotion_intensity = 5.0  # 默认中等强度
    else:
        dominant_emotion, emotion_intensity = get_dominant_emotion(emotion_embedding)
    
    # 3. 确定基础阶段（4轮一个周期）
    base_phase = ((current_round - 1) % 4) + 1
    
    # 4. 根据情绪调整阶段
    adjusted_phase = adjust_phase_by_emotion(
        base_phase, dominant_emotion, emotion_intensity, conversation_history
    )
    
    # 5. 获取阶段配置
    phase_config = CONVERSATION_PHASES.get(adjusted_phase, CONVERSATION_PHASES[1])
    
    # 6. 根据情绪调整策略权重
    strategy_weights = calculate_strategy_weights(
        phase_config["primary"],
        phase_config["secondary"],
        dominant_emotion,
        emotion_intensity
    )
    
    # 7. 确定下一阶段提示
    next_phase = adjusted_phase + 1 if adjusted_phase < 4 else 1
    next_phase_config = CONVERSATION_PHASES.get(next_phase, CONVERSATION_PHASES[1])
    
    # 8. 生成策略选择理由
    reasoning = generate_strategy_reasoning(
        current_round, adjusted_phase, dominant_emotion, 
        emotion_intensity, phase_config
    )
    
    return StrategyPlan(
        current_round=current_round,
        total_planned_rounds=4,
        current_phase=phase_config["name"],
        primary_strategy=phase_config["primary"].value,
        secondary_strategy=phase_config["secondary"].value if phase_config["secondary"] else None,
        strategy_weights=strategy_weights,
        phase_goal=phase_config["goal"],
        next_phase_hint=f"下一阶段：{next_phase_config['name']} - {next_phase_config['goal']}",
        reasoning=reasoning
    )


def calculate_strategy_weights(
    primary: SupportStrategy,
    secondary: Optional[SupportStrategy],
    dominant_emotion: str,
    emotion_intensity: float
) -> Dict[str, float]:
    """
    计算各策略的权重
    
    Args:
        primary: 主策略
        secondary: 辅助策略
        dominant_emotion: 主导情绪
        emotion_intensity: 情绪强度
    
    Returns:
        策略权重字典
    """
    weights = {s.value: 0.0 for s in SupportStrategy}
    
    # 基础权重
    weights[primary.value] = 0.6
    if secondary:
        weights[secondary.value] = 0.25
    
    # 根据情绪调整
    emotion_rules = EMOTION_STRATEGY_RULES.get(dominant_emotion, {})
    preferred = emotion_rules.get("preferred", [])
    avoid = emotion_rules.get("avoid", [])
    
    # 增加偏好策略权重
    for strategy in preferred:
        if strategy.value in weights:
            weights[strategy.value] = min(weights[strategy.value] + 0.1, 0.7)
    
    # 降低避免策略权重
    for strategy in avoid:
        if strategy.value in weights:
            weights[strategy.value] = max(weights[strategy.value] - 0.2, 0.0)
    
    # 归一化
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    
    # 只返回非零权重
    return {k: round(v, 3) for k, v in weights.items() if v > 0}


def generate_strategy_reasoning(
    current_round: int,
    phase: int,
    dominant_emotion: str,
    emotion_intensity: float,
    phase_config: Dict
) -> str:
    """生成策略选择理由"""
    emotion_note = EMOTION_STRATEGY_RULES.get(dominant_emotion, {}).get("note", "")
    
    reasoning = (
        f"当前是第{current_round}轮对话，处于「{phase_config['name']}」阶段。"
        f"检测到用户主要情绪为{dominant_emotion}（强度{emotion_intensity:.1f}）。"
    )
    
    if emotion_note:
        reasoning += f" {emotion_note}。"
    
    reasoning += f" 本轮目标：{phase_config['goal']}。"
    
    return reasoning


def generate_strategy_prompt(strategy_plan: StrategyPlan) -> str:
    """
    根据策略规划生成系统提示词片段
    
    Args:
        strategy_plan: 策略规划结果
    
    Returns:
        用于系统提示词的策略指导文本
    """
    phase_config = CONVERSATION_PHASES.get(
        ((strategy_plan.current_round - 1) % 4) + 1, 
        CONVERSATION_PHASES[1]
    )
    
    # 策略中文名映射
    strategy_cn = {
        "Reflection of Feelings": "情感反映（识别并反馈用户的情绪）",
        "Affirmation and Reassurance": "肯定安抚（肯定用户的价值和努力）",
        "Self-disclosure": "自我表露（适当分享类似经历）",
        "Providing Suggestions": "提供建议（给出具体可行的建议）",
        "Information": "提供信息（提供有用的事实或资源）",
        "Restatement or Paraphrasing": "复述确认（用自己的话重复用户的内容）",
        "Question": "提问引导（通过提问引导用户表达）"
    }
    
    primary_cn = strategy_cn.get(strategy_plan.primary_strategy, strategy_plan.primary_strategy)
    secondary_cn = strategy_cn.get(strategy_plan.secondary_strategy, "") if strategy_plan.secondary_strategy else ""
    
    # 简洁的策略指导，不显示轮次
    prompt = f"""请采用{primary_cn.split('（')[0]}的方式回应用户。{phase_config['prompt_hint']}
请直接用自然的对话方式回复，像朋友聊天一样，不要输出任何格式标记。"""
    
    return prompt


def get_strategy_for_generation(
    conversation_history: Optional[List[Dict]] = None,
    emotion_embedding: Optional[List[float]] = None,
    emotion_label: Optional[str] = None,
    user_input: str = ""
) -> Tuple[StrategyPlan, str]:
    """
    获取策略规划和对应的提示词
    
    Args:
        conversation_history: 对话历史
        emotion_embedding: 8维情绪向量
        emotion_label: 情绪标签
        user_input: 当前用户输入
    
    Returns:
        (策略规划, 策略提示词)
    """
    plan = plan_strategy(
        conversation_history=conversation_history,
        emotion_embedding=emotion_embedding,
        emotion_label=emotion_label,
        user_input=user_input
    )
    
    prompt = generate_strategy_prompt(plan)
    
    return plan, prompt
