from ..state import ConversationState


def negotiation_node(state: ConversationState) -> ConversationState:
    """
    多模型协商节点（占位实现）：
    - 情绪协商已经在 enhanced_negotiate 中完成
    - 这里可以在未来加入更多“策略协商 / 角色选择”的逻辑
    """
    state["negotiation_detail"] = {
        "used_enhanced_negotiate": True,
    }
    return state