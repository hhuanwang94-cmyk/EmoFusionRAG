#import json
#import os
#import sys
#from typing import List, Dict, Any
#
## 确保项目根目录在 sys.path 中
#_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # langgraph_app/nodes
#_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))  # 项目根目录
#if _PROJECT_ROOT not in sys.path:
#    sys.path.insert(0, _PROJECT_ROOT)
#
#from ..state import ConversationState
##from hhsoulchatshuju import enhanced_negotiate
#from langgraph_app.services.emotion_analysis_service import run_emotion_analysis
#
#
#
#def emotion_node(state: ConversationState) -> ConversationState:
#    """
#    情绪识别节点：
#    - 调用 enhanced_negotiate(user_query)
#    - 尝试解析为 8 维情绪 embedding
#    """
#    query = state.get("user_query", "")
#    if not query:
#        return state
#
#    raw_response = enhanced_negotiate(query)
#    state["emotion_raw_response"] = raw_response
#
#    emotions = ["joy", "acceptance", "fear", "surprise",
#                "sadness", "disgust", "anger", "anticipation"]
#    emotion_embedding: List[float] = [1.0] * 8
#    emotion_list: List[Dict[str, Any]] = []
#
#    try:
#        parsed = json.loads(raw_response)
#        if isinstance(parsed, list):
#            emotion_list = parsed
#            for item in parsed:
#                dim = item.get("dim")
#                score = float(item.get("score", 1.0))
#                if dim in emotions:
#                    idx = emotions.index(dim)
#                    emotion_embedding[idx] = score
#    except Exception:
#        # 解析失败则使用默认 1.0 兜底
#        pass
#
#    state["emotion_list"] = emotion_list
#    state["emotion_embedding"] = emotion_embedding
#    return state
# langgraph_app/nodes/emotion_node.py


# langgraph_app/nodes/emotion_node.py
import json
import os
import sys
from typing import List, Dict, Any

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ..state import ConversationState
from langgraph_app.services.emotion_analysis_service import run_emotion_analysis


def emotion_node(state: ConversationState) -> ConversationState:
    query = state.get("user_query", "")
    if not query:
        return state

    # ✅ 新版情绪分析流程
    final_vector_str, consensus, debug_info = run_emotion_analysis(query)

    state["emotion_raw_response"] = final_vector_str
    state["emotion_debug"] = debug_info
    state["emotion_consensus"] = consensus

    emotions = ["joy", "acceptance", "fear", "surprise",
                "sadness", "disgust", "anger", "anticipation"]
    emotion_embedding: List[float] = [1.0] * 8
    emotion_list: List[Dict[str, Any]] = []

    try:
        parsed = json.loads(final_vector_str)
        if isinstance(parsed, list):
            emotion_list = parsed
            for item in parsed:
                dim = item.get("dim")
                score = float(item.get("score", 1.0))
                if dim in emotions:
                    idx = emotions.index(dim)
                    emotion_embedding[idx] = score
    except Exception:
        pass

    state["emotion_list"] = emotion_list
    state["emotion_embedding"] = emotion_embedding
    return state
