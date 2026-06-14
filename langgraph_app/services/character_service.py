# langgraph_app/services/character_service.py

# 兼容 Python 3.8
from typing import Any, Dict, List, Optional, Tuple
import json
import os
import sys

# 项目路径配置，自动检测项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 全局缓存
_character_profiles_cache: Optional[Dict[str, Dict[str, Any]]] = None
_style_support_cache: Optional[list] = None


def _load_character_profiles() -> Dict[str, Dict[str, Any]]:
    """
    加载角色基本信息（从 character_profiles.json）
    使用缓存避免重复加载
    """
    global _character_profiles_cache
    
    if _character_profiles_cache is not None:
        return _character_profiles_cache
    
    # 尝试多个可能的路径
    possible_paths = [
        # 老路径：项目根目录 / character_rag 目录
        "character_rag/character_profiles.json",
        "../character_rag/character_profiles.json",
        "../../character_rag/character_profiles.json",
        f"{PROJECT_ROOT}/character_rag/character_profiles.json",
        f"{PROJECT_ROOT}/character_profiles.json",
        "character_profiles.json",
        # 新路径：data 目录下
        "data/character_profiles.json",
        f"{PROJECT_ROOT}/data/character_profiles.json",
    ]
    
    character_profiles = {}
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    character_profiles = json.load(f)
                print(f"✅ [character_service] 成功加载角色信息: {path}")
                break
            except Exception as e:
                print(f"⚠️ [character_service] 读取角色文件失败 {path}: {e}")
                continue
    
    if not character_profiles:
        print(f"⚠️ [character_service] 未找到角色信息文件，使用空字典")
    
    # 缓存结果
    _character_profiles_cache = character_profiles
    return character_profiles


def _load_style_support() -> list:
    """
    加载角色风格和支持策略信息（从 character_get_fengge_style_support_seven.json）
    使用缓存避免重复加载
    """
    global _style_support_cache
    
    if _style_support_cache is not None:
        return _style_support_cache
    
    # 尝试多个可能的路径
    possible_paths = [
        # 老路径：项目根目录
        "character_get_fengge_style_support_seven.json",
        "../character_get_fengge_style_support_seven.json",
        "../../character_get_fengge_style_support_seven.json",
        f"{PROJECT_ROOT}/character_get_fengge_style_support_seven.json",
        # 新路径：data 目录下
        "data/character_get_fengge_style_support_seven.json",
        f"{PROJECT_ROOT}/data/character_get_fengge_style_support_seven.json",
    ]
    
    style_support_list = []
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    style_support_list = json.load(f)
                print(f"✅ [character_service] 成功加载风格信息: {path}")
                break
            except Exception as e:
                print(f"⚠️ [character_service] 读取风格文件失败 {path}: {e}")
                continue
    
    if not style_support_list:
        print(f"⚠️ [character_service] 未找到风格信息文件，使用空列表")
    
    # 缓存结果
    _style_support_cache = style_support_list
    return style_support_list


def get_character_profile(character_name: str) -> Dict[str, Any]:
    """
    获取完整的角色配置信息
    
    参数:
        character_name: 角色名称（如 "老默"、"许红豆"、"高启强"、"稳重倾听者·阿远" 等）
    
    返回:
        包含以下字段的字典:
        - 基本信息（从 character_profiles.json）
        - style_support: 完整的风格和支持策略信息
        - style_prompt: 风格提示词
        - support_strategy: 支持策略
        - support_types: 支持类型列表
    """
    if not character_name:
        # 返回默认支持者配置
        return {
            "姓名": "支持者",
            "角色描述": "一个温和、理解、支持性的情感支持角色",
            "style_support": "",
            "style_prompt": "温和、理解、支持性的对话风格",
            "support_strategy": "",
            "support_types": []
        }
    
    # 🔧 处理带描述的角色名称（如 "稳重倾听者·阿远" -> "阿远"）
    # 如果角色名称包含 "·"，提取后面的部分
    if "·" in character_name:
        character_name = character_name.split("·")[-1].strip()
    
    # 加载角色基本信息
    character_profiles = _load_character_profiles()
    base_profile = character_profiles.get(character_name, {})
    
    # 加载风格信息
    style_support_list = _load_style_support()
    style_info = None
    
    # 查找匹配的风格信息
    for item in style_support_list:
        if item.get("character") == character_name:
            style_info = item
            break
    
    # 合并信息
    full_profile = {
        **base_profile,  # 基本信息（姓名、MBTI、性别、工作等）
    }
    
    # 添加风格信息（如果找到）
    if style_info:
        full_profile["style_support"] = style_info.get("style_support", "")
        full_profile["style_prompt"] = style_info.get("style_prompt", "")
        full_profile["support_strategy"] = style_info.get("support_strategy", "")
        full_profile["support_types"] = style_info.get("support_types", [])
        print(f"✅ [character_service] 成功加载角色 {character_name} 的完整信息（包含风格）")
    else:
        # 如果没有找到风格信息，使用默认值
        full_profile["style_support"] = ""
        full_profile["style_prompt"] = "温和、理解、支持性的对话风格"
        full_profile["support_strategy"] = ""
        full_profile["support_types"] = []
        print(f"⚠️ [character_service] 角色 {character_name} 未找到风格信息，使用默认值")
    
    # 如果基本信息也为空，至少返回角色名称
    if not base_profile:
        full_profile["姓名"] = character_name
        full_profile["角色描述"] = f"角色：{character_name}"
    
    return full_profile


def _extract_candidate_from_bm25(
    bm25_results: Optional[List[Dict[str, Any]]]
) -> Optional[Tuple[str, str]]:
    """
    尝试从 BM25 检索结果中抽取一个角色名称和简介。
    这里只是一个占位实现，根据你自己的数据结构可以自行修改。
    """
    if not bm25_results:
        return None

    for item in bm25_results:
        # 根据你的 BM25 返回结构，尝试拿到角色名和简介
        # 比如：{"character_name": "...", "character_desc": "..."}
        name = (
            item.get("character_name")
            or item.get("role_name")
            or item.get("name")
        )
        desc = (
            item.get("character_desc")
            or item.get("role_desc")
            or item.get("description")
        )
        if name:
            return name, (desc or "一位会耐心倾听你心事的陪伴者。")

    return None


def match_character(
    user_input: str,
    bm25_results: Optional[List[Dict[str, Any]]] = None,
    emotion_embedding: Optional[List[float]] = None,
    use_mcts: bool = True,  # 是否使用MCTS三阶段框架
) -> Tuple[str, str, Dict[str, float], Optional[List[float]]]:
    """
    动态角色匹配与信息检索模块
    
    支持两种模式：
    1. MCTS三阶段框架（默认）：量化-筛选-探索
       - 第一阶段：角色人格量化（MBTI 4维向量）
       - 第二阶段：Top-K候选筛选（策略适配 + 共情度）
       - 第三阶段：MCTS对话路径探索（蒙特卡洛树搜索）
    
    2. 传统三层加权匹配：
       - 策略适配分(0.5) + 语义适配分(0.3) + 关键词适配分(0.2)
    """
    # 尝试使用MCTS三阶段框架
    if use_mcts:
        try:
            from .mcts_character_service import mcts_character_match
            
            # 转换bm25_results格式
            bm25_tuples = None
            if bm25_results:
                bm25_tuples = []
                for item in bm25_results:
                    if isinstance(item, tuple):
                        bm25_tuples.append(item)
                    elif isinstance(item, dict):
                        text = item.get("text", "") or item.get("content", "")
                        score = item.get("score", 0.5)
                        bm25_tuples.append((text, score))
            
            matched_character, role_desc, weight_dict, fusion_mbti, candidate_scores = mcts_character_match(
                user_input=user_input,
                bm25_results=bm25_tuples,
                emotion_embedding=emotion_embedding,
                top_k=4,
                mcts_iterations=50
            )
            
            if matched_character:
                print(f"✅ [match_character] MCTS三阶段匹配完成")
                # 返回主角色 + 融合权重 + 融合MBTI向量
                return matched_character, role_desc, weight_dict or {}, fusion_mbti
                
        except Exception as e:
            import traceback
            print(f"⚠️ [match_character] MCTS匹配失败: {e}")
            traceback.print_exc()
            print("回退到传统匹配模式...")
    
    # 传统模式：三层加权匹配
    try:
        matched_character, role_desc = _dynamic_character_match(
            user_input, bm25_results, emotion_embedding
        )
        if matched_character:
            print(f"✅ [match_character] 传统动态匹配成功: {matched_character}")
            return matched_character, role_desc, {}, None
    except Exception as e:
        print(f"⚠️ [match_character] 传统动态匹配失败: {e}，使用备用匹配")
    
    # 备用：简单关键词匹配
    name, desc = _fallback_keyword_match(user_input, bm25_results)
    return name, desc, {}, None


def _dynamic_character_match(
    user_input: str,
    bm25_results: Optional[List[Dict[str, Any]]] = None,
    emotion_embedding: Optional[List[float]] = None,
) -> Tuple[Optional[str], str]:
    """
    动态角色匹配核心逻辑
    
    实现论文中的三层加权匹配：
    - 第一层：支持策略适配度 (权重0.5)
    - 第二层：语义相似度检索 (权重0.3)  
    - 第三层：BM25关键词检索 (权重0.2)
    """
    import json
    from scipy.spatial import distance
    
    # 加载必要的数据
    character_profiles = _load_character_profiles()
    style_support = _load_style_support()
    
    # 加载MBTI角色数据
    mbti_characters = _load_mbti_characters()
    if not mbti_characters:
        return None, ""
    
    # 初始化角色得分
    character_scores = {}
    for char_name in mbti_characters:
        character_scores[char_name] = {
            "策略适配分": 0.0,
            "语义适配分": 0.0,
            "关键词适配分": 0.0,
        }
    
    # === 第一层：支持策略适配度 (权重0.5) ===
    print(f"🔍 [动态匹配] emotion_embedding: {emotion_embedding is not None}, style_support: {len(style_support) if style_support else 0}条")
    
    # 即使没有情绪嵌入，也使用默认策略得分
    strategy_scores = _calculate_strategy_scores(emotion_embedding)
    if style_support:
        matched_style_count = 0
        # 调试：显示前3个style_support中的角色名称
        style_char_names = [item.get("character", "") for item in style_support[:5]]
        mbti_sample = list(character_scores.keys())[:5]
        print(f"🔍 [动态匹配] style_support角色示例: {style_char_names}")
        print(f"🔍 [动态匹配] MBTI角色示例: {mbti_sample}")
        
        for style_item in style_support:
            char_name = style_item.get("character", "")
            support_types = style_item.get("support_types", [])
            if char_name in character_scores:
                matched_style_count += 1
                for support_type in support_types:
                    if support_type in strategy_scores:
                        character_scores[char_name]["策略适配分"] += strategy_scores[support_type]
        print(f"🔍 [动态匹配] 策略适配匹配到 {matched_style_count} 个角色")
        
        if matched_style_count == 0:
            print(f"⚠️ [动态匹配] 角色名称不匹配！请检查 style_support 和 MBTI 角色列表")
    else:
        print(f"⚠️ [动态匹配] style_support 为空，跳过策略适配")
    
    # === 第二层：语义相似度检索 (权重0.3) ===
    semantic_results = _semantic_retrieval(user_input, mbti_characters)
    for char_name, score in semantic_results:
        if char_name in character_scores:
            character_scores[char_name]["语义适配分"] = score
    
    # === 第三层：BM25关键词检索 (权重0.2) ===
    print(f"🔍 [动态匹配] bm25_results: {len(bm25_results) if bm25_results else 0}条")
    if bm25_results:
        # 调试：显示BM25结果的格式
        if bm25_results:
            first_item = bm25_results[0]
            print(f"🔍 [动态匹配] BM25结果格式: {type(first_item)}, 内容预览: {str(first_item)[:100]}...")
        
        bm25_scores = _extract_bm25_scores(bm25_results, mbti_characters)
        print(f"🔍 [动态匹配] BM25提取到 {len(bm25_scores)} 个角色得分")
        if bm25_scores:
            print(f"🔍 [动态匹配] BM25角色得分示例: {bm25_scores[:3]}")
        for char_name, score in bm25_scores:
            if char_name in character_scores:
                character_scores[char_name]["关键词适配分"] = score
    else:
        print(f"⚠️ [动态匹配] bm25_results 为空，跳过关键词适配")
    
    # === 计算加权总分并选择最优角色 ===
    final_scores = []
    for char_name, scores in character_scores.items():
        total = (scores["策略适配分"] * 0.5 + 
                 scores["语义适配分"] * 0.3 + 
                 scores["关键词适配分"] * 0.2)
        final_scores.append((char_name, total, scores))
    
    # 按总分排序
    final_scores.sort(key=lambda x: x[1], reverse=True)
    
    if final_scores and final_scores[0][1] > 0:
        best_char = final_scores[0][0]
        scores = final_scores[0][2]
        print(f"🎯 [动态匹配] 最优角色: {best_char}")
        print(f"   策略适配分: {scores['策略适配分']:.2f} (×0.5)")
        print(f"   语义适配分: {scores['语义适配分']:.2f} (×0.3)")
        print(f"   关键词适配分: {scores['关键词适配分']:.2f} (×0.2)")
        print(f"   总得分: {final_scores[0][1]:.2f}")
        
        # 获取角色描述
        role_desc = _get_character_description(best_char, character_profiles)
        return best_char, role_desc
    
    return None, ""


def _load_mbti_characters() -> List[str]:
    """加载MBTI角色列表"""
    try:
        possible_paths = [
            "character_rag/character_mbti.json",
            f"{PROJECT_ROOT}/character_rag/character_mbti.json",
        ]
        for path in possible_paths:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    mbti_data = json.load(f)
                characters = []
                for mbti_type, char_list in mbti_data.items():
                    characters.extend(char_list)
                print(f"✅ 加载 {len(characters)} 个MBTI角色")
                return characters
    except Exception as e:
        print(f"⚠️ 加载MBTI角色失败: {e}")
    return []


def _calculate_strategy_scores(emotion_embedding: List[float]) -> Dict[str, float]:
    """根据情绪嵌入计算支持策略得分"""
    # 默认策略得分（可以通过LLM动态计算）
    return {
        "Reflection of Feelings": 7,
        "Affirmation and Reassurance": 6,
        "Self-disclosure": 5,
        "Providing Suggestions": 6,
        "Information": 4,
        "Restatement or Paraphrasing": 5,
        "Question": 6
    }


def _semantic_retrieval(
    user_input: str, 
    mbti_characters: List[str]
) -> List[Tuple[str, float]]:
    """语义相似度检索"""
    try:
        # 加载角色对话嵌入数据
        embedding_path = "data/duo/duo_memory_context_embedding_data.json"
        if not os.path.exists(embedding_path):
            embedding_path = f"{PROJECT_ROOT}/data/duo/duo_memory_context_embedding_data.json"
        
        if not os.path.exists(embedding_path):
            return []
        
        with open(embedding_path, "r", encoding="utf-8") as f:
            embedding_data = json.load(f)
        
        # 生成用户输入的简单嵌入（实际应使用嵌入模型）
        import hashlib
        text_hash = hashlib.md5(user_input.encode()).hexdigest()
        query_embedding = [float(int(text_hash[i:i+2], 16)) / 255.0 
                          for i in range(0, min(32, len(text_hash)), 2)]
        
        # 计算与每个角色的相似度
        results = []
        for char_name in mbti_characters:
            if char_name in embedding_data:
                char_contexts = embedding_data[char_name]
                max_sim = 0.0
                for ctx in char_contexts[:5]:  # 只取前5个上下文
                    ctx_emb = ctx.get("context_embedding", [])
                    if ctx_emb:
                        # 调整维度
                        min_len = min(len(query_embedding), len(ctx_emb))
                        q_emb = query_embedding[:min_len]
                        c_emb = ctx_emb[:min_len]
                        try:
                            from scipy.spatial import distance
                            sim = 1 - distance.cosine(q_emb, c_emb)
                            max_sim = max(max_sim, sim)
                        except:
                            pass
                if max_sim > 0:
                    results.append((char_name, max_sim))
        
        # 归一化
        if results:
            max_score = max(r[1] for r in results)
            min_score = min(r[1] for r in results)
            if max_score > min_score:
                results = [(name, (score - min_score) / (max_score - min_score)) 
                          for name, score in results]
        
        return sorted(results, key=lambda x: x[1], reverse=True)[:10]
    except Exception as e:
        print(f"⚠️ 语义检索失败: {e}")
        return []


def _extract_bm25_scores(
    bm25_results: List, 
    mbti_characters: List[str]
) -> List[Tuple[str, float]]:
    """
    从BM25结果中提取角色得分
    
    BM25返回格式: List[Tuple[str, float]] = [(doc_text, score), ...]
    """
    import re
    results = []
    
    for item in bm25_results:
        # 处理两种可能的格式
        if isinstance(item, tuple) and len(item) == 2:
            # BM25 返回的 (doc_text, score) 格式
            text, score = item
        elif isinstance(item, dict):
            # 字典格式
            text = item.get("text", "") or item.get("content", "") or str(item)
            score = item.get("score", 0.5)
        else:
            text = str(item)
            score = 0.5
        
        # 尝试匹配角色名称
        for char_name in mbti_characters:
            if char_name in text:
                results.append((char_name, score))
                break
    
    # 归一化
    if results:
        max_score = max(r[1] for r in results)
        min_score = min(r[1] for r in results)
        if max_score > min_score:
            results = [(name, (score - min_score) / (max_score - min_score)) 
                      for name, score in results]
        else:
            # 所有分数相同时，设为1.0
            results = [(name, 1.0) for name, _ in results]
    
    return results


def _get_character_description(char_name: str, profiles: Dict) -> str:
    """获取角色描述"""
    if char_name in profiles:
        profile = profiles[char_name]
        personality = profile.get("人物性格", "")
        experience = profile.get("人物经历", "")
        if personality:
            return f"性格特点：{personality[:100]}"
        if experience:
            return f"经历：{experience[:100]}"
    return f"一位善于倾听、提供情感支持的陪伴者。"


def _fallback_keyword_match(
    user_input: str,
    bm25_results: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, str]:
    """备用：简单关键词匹配"""
    # 尝试从 BM25 结果中抽取
    candidate = _extract_candidate_from_bm25(bm25_results)
    if candidate is not None:
        return candidate

    text = user_input or ""

    # 关键词匹配规则
    keyword_rules = [
        (["崩溃", "不想活", "绝望", "撑不住", "想死"], 
         "安欣", "一位正直温和的倾听者，会用真诚和耐心陪伴你度过最艰难的时刻。"),
        (["压力", "很累", "焦虑", "委屈", "没动力", "提不起劲", "工作"], 
         "史强", "一位务实直接的朋友，擅长帮你理清思路、分析问题。"),
        (["失恋", "分手", "感情", "恋爱", "吵架"], 
         "甄嬛", "一位经历丰富、善于理解复杂情感的知心姐姐。"),
        (["孤独", "没人", "一个人", "被冷落"], 
         "佟湘玉", "一位热情开朗的大姐，会用温暖和幽默化解你的孤独感。"),
        (["难过", "伤心", "哭", "低落", "郁闷"], 
         "许红豆", "一位温柔善解人意的朋友，会静静陪在你身边。"),
    ]

    for keywords, char_name, desc in keyword_rules:
        if any(kw in text for kw in keywords):
            return char_name, desc

    # 默认角色
    return "许红豆", "一位温柔善解人意的朋友，会以温和的方式陪你聊天。"


def get_all_character_names() -> list:
    """
    获取所有可用的角色名称列表
    
    返回:
        角色名称列表
    """
    character_profiles = _load_character_profiles()
    return list(character_profiles.keys())


def clear_cache():
    """
    清除缓存（用于重新加载数据）
    """
    global _character_profiles_cache, _style_support_cache
    _character_profiles_cache = None
    _style_support_cache = None
    print("✅ [character_service] 缓存已清除")