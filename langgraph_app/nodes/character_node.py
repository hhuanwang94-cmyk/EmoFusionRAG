from ..state import ConversationState
from ..services.character_service import get_character_profile


def character_node(state: ConversationState) -> ConversationState:
    """
    角色人格 / 风格装配节点：
    - 根据 selected_character 加载角色画像
    - 🔧 修复：从 profile 中提取 style_support 信息并存储到 state
    """
    selected_character = state.get("selected_character") or "支持者"
    
    # 获取完整的角色信息（包含基本信息 + 风格信息）
    profile = get_character_profile(selected_character)
    
    # 存储基本信息
    state["selected_character"] = selected_character
    state["character_profile"] = profile
    
    # 🔧 从 profile 中提取风格和支持策略信息
    if isinstance(profile, dict):
        # 提取风格信息
        style_support = profile.get("style_support", "")
        style_prompt = profile.get("style_prompt", "")
        support_strategy = profile.get("support_strategy", "")
        support_types = profile.get("support_types", [])
        
        # 存储到 state 中，供 generation_node 使用
        state["character_style"] = style_support  # 完整的风格和支持策略信息
        state["character_style_prompt"] = style_prompt  # 风格提示词
        state["support_strategy"] = support_strategy  # 支持策略
        state["support_types"] = support_types  # 支持类型列表
        
        # 调试信息
        print(f"✅ [character_node] 角色: {selected_character}")
        print(f"🔍 [character_node] 风格信息长度: {len(style_support)} 字符")
        print(f"🔍 [character_node] 支持类型: {support_types}")
        
        # 如果风格信息为空，打印警告
        if not style_support:
            print(f"⚠️ [character_node] 角色 {selected_character} 的风格信息为空")
    else:
        # 如果 profile 不是字典，使用默认值
        state["character_style"] = ""
        state["character_style_prompt"] = "温和、理解、支持性的对话风格"
        state["support_strategy"] = ""
        state["support_types"] = []
        print(f"⚠️ [character_node] 角色 {selected_character} 的配置格式异常，使用默认值")
    
    return state