# langgraph_app/services/mcts_character_service.py
"""
三阶段智能决策框架：量化-筛选-探索
1. 角色人格量化：基于MBTI理论的4维风格向量
2. Top-K候选角色筛选：支持策略适配度 + 共情度评估
3. 基于MCTS的对话路径探索：蒙特卡洛树搜索优化角色融合权重
"""

from typing import Any, Dict, List, Optional, Tuple
import json
import os
import sys
import math
import random
import numpy as np
from dataclasses import dataclass, field

# 动态推断项目根目录
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # langgraph_app/services
PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))  # 项目根目录
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 第一阶段：角色人格量化 - MBTI 4维风格向量
# ============================================================

@dataclass
class MBTIVector:
    """MBTI 4维风格向量"""
    E_I: float = 50.0  # 外向(E) vs 内向(I), 0-100, 高分=外向
    S_N: float = 50.0  # 感觉(S) vs 直觉(N), 0-100, 高分=直觉
    T_F: float = 50.0  # 思考(T) vs 情感(F), 0-100, 高分=情感
    J_P: float = 50.0  # 判断(J) vs 知觉(P), 0-100, 高分=知觉
    
    def to_array(self) -> np.ndarray:
        """转换为numpy数组（归一化到0-1）"""
        return np.array([self.E_I, self.S_N, self.T_F, self.J_P]) / 100.0
    
    @classmethod
    def from_array(cls, arr: np.ndarray) -> 'MBTIVector':
        """从numpy数组创建（假设已归一化）"""
        arr = arr * 100.0
        return cls(E_I=arr[0], S_N=arr[1], T_F=arr[2], J_P=arr[3])
    
    def cosine_similarity(self, other: 'MBTIVector') -> float:
        """计算与另一个MBTI向量的余弦相似度"""
        v1 = self.to_array()
        v2 = other.to_array()
        dot = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)


@dataclass
class CharacterProfile:
    """角色画像"""
    name: str
    mbti_vector: MBTIVector
    support_types: List[str] = field(default_factory=list)
    personality: str = ""
    experience: str = ""
    empathy_score: float = 0.0  # 共情度得分
    strategy_score: float = 0.0  # 策略适配得分


# 全局缓存
_mbti_vectors_cache: Optional[Dict[str, MBTIVector]] = None
_character_profiles_cache: Optional[Dict[str, CharacterProfile]] = None

#真正的语义检索
# 语义向量模型缓存（BGE）
_bge_model = None
_bge_model_path: Optional[str] = None
_char_text_cache: Dict[str, str] = {}
_char_emb_cache: Dict[str, np.ndarray] = {}


def _resolve_bge_model_path() -> Optional[str]:
    """解析 BGE 模型路径。

    优先级：环境变量 BGE_MODEL_PATH -> utils.config.BGEModel_PATH -> None
    """
    env_path = (os.environ.get("BGE_MODEL_PATH") or "").strip()
    if env_path:
        return env_path

    try:
        from utils.config import BGEModel_PATH  # type: ignore
        cfg_path = (BGEModel_PATH or "").strip()
        if cfg_path:
            return cfg_path
    except Exception:
        pass

    return None


def _get_bge_model():
    """懒加载 BGE embedding 模型。

    - 使用 sentence-transformers 以最少代码实现 embedding。
    - 若依赖或模型不可用，返回 None（上层会回退到简化语义）。
    """
    global _bge_model, _bge_model_path

    if _bge_model is not None:
        return _bge_model

    model_path = _resolve_bge_model_path()
    _bge_model_path = model_path
    if not model_path:
        print("⚠️ [MCTS] 未配置 BGE 模型路径：请设置环境变量 BGE_MODEL_PATH 或 utils.config.BGEModel_PATH")
        return None

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as e:
        print(f"⚠️ [MCTS] 未安装 sentence-transformers，无法计算真实语义向量，将回退简化语义。错误: {e}")
        return None

    try:
        print(f"🔍 [MCTS] 加载 BGE 向量模型: {model_path}")
        _bge_model = SentenceTransformer(model_path)
        return _bge_model
    except Exception as e:
        print(f"⚠️ [MCTS] BGE 向量模型加载失败，将回退简化语义。错误: {e}")
        _bge_model = None
        return None
#语义检索结束
def load_mbti_vectors() -> Dict[str, MBTIVector]:
    """
    加载所有角色的MBTI向量
    从 characters_label.json 读取
    """
    global _mbti_vectors_cache
    if _mbti_vectors_cache is not None:
        return _mbti_vectors_cache
    
    possible_paths = [
        f"{PROJECT_ROOT}/data/characters_label.json",
        "data/characters_label.json",
        "../data/characters_label.json",
    ]
    
    mbti_vectors = {}
    
    for path in possible_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # 解析 pdb 格式
                pdb_data = data.get("pdb", data)
                for char_name, char_data in pdb_data.items():
                    if "16Personalities" in char_data:
                        mbti = char_data["16Personalities"]
                        mbti_vectors[char_name] = MBTIVector(
                            E_I=mbti.get("E/I", {}).get("score", 50.0),
                            S_N=mbti.get("S/N", {}).get("score", 50.0),
                            T_F=mbti.get("T/F", {}).get("score", 50.0),
                            J_P=mbti.get("P/J", {}).get("score", 50.0),
                        )
                
                # 加载成功，不打印详细信息
                break
            except Exception as e:
                print(f"⚠️ [MCTS] 加载MBTI向量失败: {e}")
                continue
    
    _mbti_vectors_cache = mbti_vectors
    return mbti_vectors


def get_ideal_mbti_for_emotion(emotion_embedding: Optional[List[float]] = None) -> MBTIVector:
    """
    根据用户情绪状态，生成理想的支持者MBTI向量
    
    情绪维度: joy, acceptance, fear, surprise, sadness, disgust, anger, anticipation
    """
    if emotion_embedding is None or len(emotion_embedding) < 8:
        # 默认：温和、共情、倾听型
        return MBTIVector(E_I=40.0, S_N=60.0, T_F=70.0, J_P=40.0)
    
    joy, acceptance, fear, surprise, sadness, disgust, anger, anticipation = emotion_embedding[:8]
    
    # 根据情绪调整理想MBTI
    # 悲伤/恐惧 -> 需要更内向、情感型的支持者
    # 愤怒 -> 需要更冷静、思考型的支持者
    # 快乐 -> 可以匹配更外向的角色
    
    e_i = 30.0 + joy * 5 - sadness * 3 - fear * 2  # 悲伤时需要安静陪伴
    s_n = 50.0 + anticipation * 3 - fear * 2  # 恐惧时需要更直觉型理解
    t_f = 60.0 + sadness * 4 + fear * 3 - anger * 2  # 悲伤/恐惧需要情感支持
    j_p = 40.0 + surprise * 2 - anger * 3  # 愤怒时需要更有条理
    
    # 限制在0-100范围
    e_i = max(0, min(100, e_i))
    s_n = max(0, min(100, s_n))
    t_f = max(0, min(100, t_f))
    j_p = max(0, min(100, j_p))
    
    return MBTIVector(E_I=e_i, S_N=s_n, T_F=t_f, J_P=j_p)


# ============================================================
# 第二阶段：Top-K候选角色筛选
# ============================================================

def calculate_strategy_adaptation_score(
    character: CharacterProfile,
    recommended_strategies: List[str]
) -> float:
    """
    计算支持策略适配度
    
    Args:
        character: 角色画像
        recommended_strategies: 推荐的支持策略列表
    
    Returns:
        适配度得分 (0-1)
    """
    if not character.support_types or not recommended_strategies:
        return 0.0
    
    # 计算策略集合的交集比例
    char_strategies = set(character.support_types)
    rec_strategies = set(recommended_strategies)
    
    intersection = len(char_strategies & rec_strategies)
    union = len(char_strategies | rec_strategies)
    
    if union == 0:
        return 0.0
    
    # Jaccard相似度
    return intersection / union


def calculate_empathy_score(
    character: CharacterProfile,
    user_input: str,
    bm25_score: float = 0.0,
    semantic_score: float = 0.0,
    alpha: float = 0.4  # BM25权重
) -> float:
    """
    计算共情度评估得分
    融合BM25关键词匹配和语义向量相似度
    
    Args:
        character: 角色画像
        user_input: 用户输入
        bm25_score: BM25得分
        semantic_score: 语义相似度得分
        alpha: BM25权重 (1-alpha为语义权重)
    
    Returns:
        共情度得分 (0-1)
    """
    # 融合BM25和语义得分
    empathy = alpha * bm25_score + (1 - alpha) * semantic_score
    return min(1.0, max(0.0, empathy))


def select_top_k_candidates(
    characters: Dict[str, CharacterProfile],
    user_input: str,
    emotion_embedding: Optional[List[float]] = None,
    bm25_scores: Optional[Dict[str, float]] = None,
    semantic_scores: Optional[Dict[str, float]] = None,
    recommended_strategies: Optional[List[str]] = None,
    k: int = 5,
    strategy_weight: float = 0.3,
    empathy_weight: float = 0.3,
    mbti_weight: float = 0.4
) -> List[CharacterProfile]:
    """
    筛选Top-K候选角色
    
    综合得分 = 策略适配度 × w1 + 共情度 × w2 + MBTI匹配度 × w3
    """
    if not characters:
        return []
    
    bm25_scores = bm25_scores or {}
    semantic_scores = semantic_scores or {}
    recommended_strategies = recommended_strategies or ["情感支持", "倾听陪伴", "共情理解"]
    
    # 获取理想MBTI向量
    ideal_mbti = get_ideal_mbti_for_emotion(emotion_embedding)
    
    scored_characters = []
    
    for name, char in characters.items():
        # 1. 策略适配度
        strategy_score = calculate_strategy_adaptation_score(char, recommended_strategies)
        
        # 2. 共情度
        bm25 = bm25_scores.get(name, 0.0)
        semantic = semantic_scores.get(name, 0.0)
        empathy_score = calculate_empathy_score(char, user_input, bm25, semantic)
        
        # 3. MBTI匹配度
        mbti_score = ideal_mbti.cosine_similarity(char.mbti_vector)
        
        # 综合得分
        total_score = (
            strategy_score * strategy_weight +
            empathy_score * empathy_weight +
            mbti_score * mbti_weight
        )
        
        # 更新角色得分
        char.strategy_score = strategy_score
        char.empathy_score = empathy_score
        
        scored_characters.append((char, total_score))
    
    # 按得分排序，取Top-K
    scored_characters.sort(key=lambda x: x[1], reverse=True)
    top_k_with_scores = scored_characters[:k]
    top_k = [char for char, score in top_k_with_scores]
    
    # 构建得分字典
    score_dict = {char.name: score for char, score in top_k_with_scores}
    
    return top_k, score_dict


# ============================================================
# 第三阶段：基于MCTS的对话路径探索
# ============================================================

@dataclass
class MCTSNode:
    """MCTS树节点"""
    weights: np.ndarray  # 角色融合权重
    parent: Optional['MCTSNode'] = None
    children: List['MCTSNode'] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0
    
    @property
    def average_reward(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.total_reward / self.visits
    
    def ucb1(self, exploration_constant: float = 1.414) -> float:
        """计算UCB1值"""
        if self.visits == 0:
            return float('inf')
        if self.parent is None or self.parent.visits == 0:
            return self.average_reward
        
        exploitation = self.average_reward
        exploration = exploration_constant * math.sqrt(
            math.log(self.parent.visits) / self.visits
        )
        return exploitation + exploration


class MCTSCharacterFusion:
    """
    基于MCTS的角色融合探索器
    
    通过蒙特卡洛树搜索，智能探索不同角色风格的融合权重，
    找到最优的角色融合策略。
    """
    
    def __init__(
        self,
        candidates: List[CharacterProfile],
        user_input: str,
        emotion_embedding: Optional[List[float]] = None,
        max_iterations: int = 100,
        exploration_constant: float = 1.414,
        simulation_depth: int = 3
    ):
        self.candidates = candidates
        self.user_input = user_input
        self.emotion_embedding = emotion_embedding
        self.max_iterations = max_iterations
        self.exploration_constant = exploration_constant
        self.simulation_depth = simulation_depth
        self.num_candidates = len(candidates)
        
        # 初始化根节点（均匀权重）
        initial_weights = np.ones(self.num_candidates) / self.num_candidates
        self.root = MCTSNode(weights=initial_weights)
    
    def search(self) -> Tuple[np.ndarray, MBTIVector]:
        """
        执行MCTS搜索
        
        Returns:
            最优权重向量, 融合后的MBTI向量
        """
        # MCTS搜索开始
        
        for iteration in range(self.max_iterations):
            # 1. 选择 (Selection)
            node = self._select(self.root)
            
            # 2. 扩展 (Expansion)
            if node.visits > 0 and len(node.children) < self._max_children():
                node = self._expand(node)
            
            # 3. 模拟 (Simulation)
            reward = self._simulate(node)
            
            # 4. 反向传播 (Backpropagation)
            self._backpropagate(node, reward)
        
        # 选择访问次数最多的子节点
        best_node = self._get_best_child(self.root, use_visits=True)
        best_weights = best_node.weights if best_node else self.root.weights
        
        # 计算融合MBTI向量
        fusion_mbti = self._compute_fusion_mbti(best_weights)
        
        # MCTS搜索完成
        
        return best_weights, fusion_mbti
    
    def _select(self, node: MCTSNode) -> MCTSNode:
        """选择阶段：使用UCB1选择最有潜力的节点"""
        while node.children:
            node = self._get_best_child(node, use_visits=False)
        return node
    
    def _expand(self, node: MCTSNode) -> MCTSNode:
        """扩展阶段：生成新的权重组合"""
        # 生成扰动权重
        perturbation = np.random.randn(self.num_candidates) * 0.1
        new_weights = node.weights + perturbation
        
        # 确保权重非负且归一化
        new_weights = np.maximum(new_weights, 0.01)
        new_weights = new_weights / new_weights.sum()
        
        child = MCTSNode(weights=new_weights, parent=node)
        node.children.append(child)
        return child
    
    def _simulate(self, node: MCTSNode) -> float:
        """
        模拟阶段：评估当前权重组合的潜在情绪改善效果
        
        使用轻量级评估：
        1. MBTI匹配度
        2. 策略覆盖度
        3. 共情度加权平均
        """
        weights = node.weights
        
        # 1. 计算融合MBTI与理想MBTI的匹配度
        fusion_mbti = self._compute_fusion_mbti(weights)
        ideal_mbti = get_ideal_mbti_for_emotion(self.emotion_embedding)
        mbti_match = fusion_mbti.cosine_similarity(ideal_mbti)
        
        # 2. 计算加权策略覆盖度
        strategy_coverage = sum(
            w * c.strategy_score 
            for w, c in zip(weights, self.candidates)
        )
        
        # 3. 计算加权共情度
        empathy_avg = sum(
            w * c.empathy_score 
            for w, c in zip(weights, self.candidates)
        )
        
        # 4. 多样性奖励（避免过度集中在单一角色）
        entropy = -sum(w * math.log(w + 1e-10) for w in weights)
        diversity_bonus = entropy / math.log(self.num_candidates + 1e-10)
        
        # 综合奖励
        reward = (
            0.3 * mbti_match +
            0.3 * strategy_coverage +
            0.3 * empathy_avg +
            0.1 * diversity_bonus
        )
        
        return reward
    
    def _backpropagate(self, node: MCTSNode, reward: float):
        """反向传播阶段：更新节点统计信息"""
        while node is not None:
            node.visits += 1
            node.total_reward += reward
            node = node.parent
    
    def _get_best_child(self, node: MCTSNode, use_visits: bool = False) -> Optional[MCTSNode]:
        """获取最佳子节点"""
        if not node.children:
            return None
        
        if use_visits:
            # 选择访问次数最多的
            return max(node.children, key=lambda c: c.visits)
        else:
            # 使用UCB1选择
            return max(node.children, key=lambda c: c.ucb1(self.exploration_constant))
    
    def _max_children(self) -> int:
        """每个节点的最大子节点数"""
        return min(10, self.num_candidates * 2)
    
    def _compute_fusion_mbti(self, weights: np.ndarray) -> MBTIVector:
        """计算融合后的MBTI向量"""
        fusion_array = np.zeros(4)
        for w, char in zip(weights, self.candidates):
            fusion_array += w * char.mbti_vector.to_array()
        return MBTIVector.from_array(fusion_array)


# ============================================================
# 主入口函数
# ============================================================

def mcts_character_match(
    user_input: str,
    bm25_results: Optional[List[Tuple[str, float]]] = None,
    emotion_embedding: Optional[List[float]] = None,
    top_k: int = 5,
    mcts_iterations: int = 50
) -> Tuple[str, str, Dict[str, float], List[float]]:
    """
    三阶段智能角色匹配主入口
    
    Args:
        user_input: 用户输入
        bm25_results: BM25检索结果 [(doc, score), ...]
        emotion_embedding: 情绪嵌入向量
        top_k: 候选角色数量
        mcts_iterations: MCTS迭代次数
    
    Returns:
        (最优角色名, 角色描述, 融合权重字典, 融合MBTI向量[EI,SN,TF,JP])
    """
    # ========== 第一阶段：角色人格量化 ==========
    mbti_vectors = load_mbti_vectors()
    
    # 加载角色画像
    characters = _load_all_character_profiles(mbti_vectors)
    if not characters:
        print("⚠️ 未找到角色数据，使用默认角色")
        return "许红豆", "温柔善解人意的朋友", {}, [50.0, 50.0, 70.0, 50.0]
    
    # ========== 第二阶段：Top-K候选筛选 ==========
    
    # 解析BM25得分
    bm25_scores = {}
    if bm25_results:
        for doc, score in bm25_results:
            for char_name in characters.keys():
                if char_name in doc:
                    bm25_scores[char_name] = max(bm25_scores.get(char_name, 0), score)
    
    # 计算语义得分（简化版，可以接入更复杂的语义模型）
    semantic_scores = _compute_semantic_scores(user_input, characters)
    
    # 根据情绪推荐策略
    recommended_strategies = _get_recommended_strategies(emotion_embedding)
    
    # 筛选Top-K
    candidates, candidate_scores = select_top_k_candidates(
        characters=characters,
        user_input=user_input,
        emotion_embedding=emotion_embedding,
        bm25_scores=bm25_scores,
        semantic_scores=semantic_scores,
        recommended_strategies=recommended_strategies,
        k=top_k
    )
    
    if not candidates:
        print("⚠️ 未筛选到候选角色，使用默认角色")
        return "许红豆", "温柔善解人意的朋友", {}, [50.0, 50.0, 70.0, 50.0], {}
    
    # 打印Top-K候选角色得分
    print(f"   Top-{len(candidates)}候选角色得分: {candidate_scores}")
    
    # ========== 第三阶段：MCTS对话路径探索 ==========
    
    mcts = MCTSCharacterFusion(
        candidates=candidates,
        user_input=user_input,
        emotion_embedding=emotion_embedding,
        max_iterations=mcts_iterations
    )
    
    best_weights, fusion_mbti = mcts.search()
    
    # 构建权重字典
    weight_dict = {
        char.name: float(w) 
        for char, w in zip(candidates, best_weights)
    }
    
    # 选择权重最高的角色作为主角色
    best_idx = np.argmax(best_weights)
    best_character = candidates[best_idx]
    
    # 生成融合描述
    role_desc = _generate_fusion_description(candidates, best_weights, fusion_mbti)
    
    
    # 融合MBTI向量以列表形式返回，便于JSON序列化
    fusion_mbti_list = [
        float(fusion_mbti.E_I),
        float(fusion_mbti.S_N),
        float(fusion_mbti.T_F),
        float(fusion_mbti.J_P),
    ]
    return best_character.name, role_desc, weight_dict, fusion_mbti_list, candidate_scores


def _load_all_character_profiles(mbti_vectors: Dict[str, MBTIVector]) -> Dict[str, CharacterProfile]:
    """加载所有角色画像"""
    from .character_service import _load_character_profiles, _load_style_support
    
    profiles_data = _load_character_profiles()
    style_support = _load_style_support()
    
    # 构建style_support查找表
    style_map = {}
    for item in style_support:
        char_name = item.get("character", "")
        if char_name:
            style_map[char_name] = item.get("support_types", [])
    
    characters = {}
    for name, mbti in mbti_vectors.items():
        profile_data = profiles_data.get(name, {})
        characters[name] = CharacterProfile(
            name=name,
            mbti_vector=mbti,
            support_types=style_map.get(name, []),
            personality=profile_data.get("人物性格", ""),
            experience=profile_data.get("人物经历", "")
        )
    
    return characters


#def _compute_semantic_scores(
#    user_input: str, 
#    characters: Dict[str, CharacterProfile]
#) -> Dict[str, float]:
#    """计算语义相似度得分（简化版）"""
#    # 这里可以接入更复杂的语义模型
#    # 目前使用简单的关键词匹配
#    scores = {}
#    keywords = set(user_input)
#    
#    for name, char in characters.items():
#        # 基于人物性格和经历的关键词匹配
#        text = char.personality + char.experience
#        overlap = len(keywords & set(text))
#        scores[name] = min(1.0, overlap / (len(keywords) + 1))
#    
#    return scores

def _compute_semantic_scores(
    user_input: str, 
    characters: Dict[str, CharacterProfile]
) -> Dict[str, float]:
    """计算语义相似度得分（BGE 向量余弦相似度；不可用时回退简化版）"""
    model = _get_bge_model()
    if model is None:
        # 回退：使用简单的字符集合重叠作为“伪语义”分数
        scores = {}
        keywords = set(user_input)

        for name, char in characters.items():
            text = (char.personality + char.experience) or ""
            overlap = len(keywords & set(text))
            scores[name] = min(1.0, overlap / (len(keywords) + 1))

        return scores

    # 真实语义：BGE embedding + cosine
    try:
        user_vec = model.encode(
            [user_input],
            normalize_embeddings=True,
            show_progress_bar=False
        )[0]
        user_vec = np.asarray(user_vec, dtype=np.float32)
    except Exception as e:
        print(f"⚠️ [MCTS] 用户文本向量化失败，将回退简化语义。错误: {e}")
        scores = {}
        keywords = set(user_input)
        for name, char in characters.items():
            text = (char.personality + char.experience) or ""
            overlap = len(keywords & set(text))
            scores[name] = min(1.0, overlap / (len(keywords) + 1))
        return scores

    scores: Dict[str, float] = {}
    for name, char in characters.items():
        role_text = ((char.personality or "") + "\n" + (char.experience or "")).strip()
        if not role_text:
            scores[name] = 0.0
            continue

        # 角色向量缓存：文本变了才重算
        cached_text = _char_text_cache.get(name)
        role_vec = _char_emb_cache.get(name)
        if cached_text != role_text or role_vec is None:
            try:
                role_vec_np = model.encode(
                    [role_text],
                    normalize_embeddings=True,
                    show_progress_bar=False
                )[0]
                role_vec = np.asarray(role_vec_np, dtype=np.float32)
                _char_text_cache[name] = role_text
                _char_emb_cache[name] = role_vec
            except Exception as e:
                print(f"⚠️ [MCTS] 角色文本向量化失败: {name}，语义分记为0。错误: {e}")
                scores[name] = 0.0
                continue

        # 因为 normalize_embeddings=True，dot 就是 cosine
        cos_sim = float(np.dot(user_vec, role_vec))
        # 将 [-1,1] 映射到 [0,1]
        scores[name] = max(0.0, min(1.0, (cos_sim + 1.0) / 2.0))

    return scores

def _get_recommended_strategies(emotion_embedding: Optional[List[float]] = None) -> List[str]:
    """根据情绪推荐支持策略"""
    default_strategies = ["情感支持", "倾听陪伴", "共情理解"]
    
    if emotion_embedding is None or len(emotion_embedding) < 8:
        return default_strategies
    
    joy, acceptance, fear, surprise, sadness, disgust, anger, anticipation = emotion_embedding[:8]
    
    strategies = []
    
    # 根据主导情绪推荐策略
    if sadness > 5:
        strategies.extend(["情感支持", "倾听陪伴", "温暖鼓励"])
    if fear > 5:
        strategies.extend(["安全感建立", "理性分析", "陪伴支持"])
    if anger > 5:
        strategies.extend(["情绪疏导", "理性引导", "换位思考"])
    if joy > 5:
        strategies.extend(["积极互动", "分享喜悦", "正向强化"])
    
    return strategies if strategies else default_strategies


def _generate_fusion_description(
    candidates: List[CharacterProfile],
    weights: np.ndarray,
    fusion_mbti: MBTIVector
) -> str:
    """生成融合角色描述"""
    # 找出权重最高的前3个角色
    top_indices = np.argsort(weights)[-3:][::-1]
    
    descriptions = []
    for idx in top_indices:
        if weights[idx] > 0.1:  # 只包含权重>10%的角色
            char = candidates[idx]
            weight_pct = int(weights[idx] * 100)
            if char.personality:
                descriptions.append(f"{char.name}的{char.personality[:20]}({weight_pct}%)")
    
    if not descriptions:
        return "温柔善解人意的朋友，会以温和的方式陪你聊天"
    
    # MBTI风格描述
    mbti_desc = []
    if fusion_mbti.E_I < 40:
        mbti_desc.append("内敛")
    elif fusion_mbti.E_I > 60:
        mbti_desc.append("开朗")
    
    if fusion_mbti.T_F > 60:
        mbti_desc.append("共情")
    else:
        mbti_desc.append("理性")
    
    style = "、".join(mbti_desc) if mbti_desc else "温和"
    
    return f"融合了{', '.join(descriptions)}的特质，以{style}的方式陪伴你"
