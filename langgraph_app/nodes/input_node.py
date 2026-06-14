from ..state import ConversationState


def input_node(state: ConversationState) -> ConversationState:
    """
    输入 / 会话包装节点：
    - 规范 user_query / history / selected_character 等字段
    """
    user_query = (state.get("user_query") or "").strip()
    history = state.get("history") or []
    selected_character = state.get("selected_character") or "支持者"

    state["user_query"] = user_query
    state["history"] = history
    state["selected_character"] = selected_character

    return state