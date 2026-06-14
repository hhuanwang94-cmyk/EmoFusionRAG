## langgraph_app/state.py
#from typing import Any, Dict, List, Optional
#from dataclasses import dataclass, field
#
#
#@dataclass
#class ConversationState:
#    # 用户输入
#    user_input: str = ""
#
#    # 基础情绪信息（如你已有的情绪识别节点结果）
#    emotion_label: Optional[str] = None
#    emotion_score: Optional[float] = None
#    emotion_embedding: Optional[List[float]] = None  # 8维情绪嵌入向量
#
#    # 是否是简单打招呼
#    is_greeting: bool = False
#    # 是否是“情感类问题”
#    is_emotional: bool = False
#
#    # 当前匹配到的角色（仅在 is_emotional = True 时才会有）
#    current_role: Optional[str] = None
#    role_description: Optional[str] = None
#    
#    # MCTS三阶段框架相关
#    character_fusion_weights: Dict[str, float] = field(default_factory=dict)  # 角色融合权重
#    mbti_fusion_vector: Optional[List[float]] = None  # 融合后的MBTI向量
#
#    # 检索结果 / 中间信息
#    bm25_results: List[Dict[str, Any]] = field(default_factory=list)
#    
#    # 多轮对话策略规划
#    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # 对话历史
#    strategy_plan: Dict[str, Any] = field(default_factory=dict)  # 策略规划结果
#    strategy_prompt: str = ""  # 策略提示词
#
#    # 最终回复
#    assistant_response: str = ""
#
#    # 调试/日志
#    debug_info: Dict[str, Any] = field(default_factory=dict)
#
#
#def state_to_dict(state: ConversationState) -> Dict[str, Any]:
#    """用于在 FastAPI 中返回 JSON。"""
#    return {
#        "user_input": state.user_input,
#        "emotion_label": state.emotion_label,
#        "emotion_score": state.emotion_score,
#        "emotion_embedding": state.emotion_embedding,
#        "is_greeting": state.is_greeting,
#        "is_emotional": state.is_emotional,
#        "current_role": state.current_role,
#        "role_description": state.role_description,
#        "character_fusion_weights": state.character_fusion_weights,
#        "mbti_fusion_vector": state.mbti_fusion_vector,
#        "bm25_results": state.bm25_results,
#        "conversation_history": state.conversation_history,
#        "strategy_plan": state.strategy_plan,
#        "strategy_prompt": state.strategy_prompt,
#        "assistant_response": state.assistant_response,
#        "debug_info": state.debug_info,
#    }
# langgraph_app/state.py
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ConversationState:
    # 用户输入
    user_input: str = ""

    # 基础情绪信息（如你已有的情绪识别节点结果）
    emotion_label: Optional[str] = None
    emotion_score: Optional[float] = None
    emotion_embedding: Optional[List[float]] = None  # 8维情绪嵌入向量

    # 是否是简单打招呼
    is_greeting: bool = False
    # 是否是“情感类问题”
    is_emotional: bool = False

    # 当前匹配到的角色（仅在 is_emotional = True 时才会有）
    current_role: Optional[str] = None
    role_description: Optional[str] = None
    
    # MCTS三阶段框架相关
    character_fusion_weights: Dict[str, float] = field(default_factory=dict)  # 角色融合权重
    mbti_fusion_vector: Optional[List[float]] = None  # 融合后的MBTI向量

    # 检索结果 / 中间信息
    bm25_results: List[Dict[str, Any]] = field(default_factory=list)
    
    # 多轮对话策略规划
    conversation_history: List[Dict[str, str]] = field(default_factory=list)  # 对话历史
    strategy_plan: Dict[str, Any] = field(default_factory=dict)  # 策略规划结果
    strategy_prompt: str = ""  # 策略提示词

    # 最终回复
    assistant_response: str = ""

    # 调试/日志
    debug_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationState:
    """用于评估流程的状态。"""
    input_filepath: str = ""
    output_filepath: str = ""
    test_data: List[Dict[str, Any]] = field(default_factory=list)
    results: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


def state_to_dict(state: ConversationState) -> Dict[str, Any]:
    """用于在 FastAPI 中返回 JSON。"""
    return {
        "user_input": state.user_input,
        "emotion_label": state.emotion_label,
        "emotion_score": state.emotion_score,
        "emotion_embedding": state.emotion_embedding,
        "is_greeting": state.is_greeting,
        "is_emotional": state.is_emotional,
        "current_role": state.current_role,
        "role_description": state.role_description,
        "character_fusion_weights": state.character_fusion_weights,
        "mbti_fusion_vector": state.mbti_fusion_vector,
        "bm25_results": state.bm25_results,
        "conversation_history": state.conversation_history,
        "strategy_plan": state.strategy_plan,
        "strategy_prompt": state.strategy_prompt,
        "assistant_response": state.assistant_response,
        "debug_info": state.debug_info,
    }
