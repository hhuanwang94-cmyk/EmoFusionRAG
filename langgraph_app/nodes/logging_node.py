import os
import sys

# 确保项目根目录在 sys.path 中
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # langgraph_app/nodes
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))  # 项目根目录
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from ..state import ConversationState
from utils.logger_config import get_logger

logger = get_logger("emotion_rag.langgraph")


def logging_node(state: ConversationState) -> ConversationState:
    """
    日志节点（可选）：
    - 记录每轮对话的输入/输出，方便调试
    """
    user_query = state.get("user_query", "")
    final_answer = state.get("final_answer", "")
    selected_character = state.get("selected_character", "")

    logger.info(f"[LangGraph] user_query={user_query}")
    logger.info(f"[LangGraph] character={selected_character}")
    logger.info(f"[LangGraph] final_answer={final_answer}")
    return state