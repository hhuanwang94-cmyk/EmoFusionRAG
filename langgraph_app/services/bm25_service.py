from typing import List, Tuple
import sys
import os

# 确保使用当前项目的 BM25 模块，而不是旧项目的
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # langgraph_app/services
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_CURRENT_DIR))  # /EmotionHH/MyEmoHH
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from BM25.bm25 import BM25


def bm25_retrieve(query: str, top_k: int = 10) -> List[Tuple[str, float]]:
    """
    使用 BM25 对角色文本进行检索
    返回 [(doc, score), ...]
    """
    bm25 = BM25()
    result = bm25.cal_similarity(query)

    # 过滤 score <= 0，并取前 top_k
    filtered = [(doc, score) for doc, score in result if score > 0]
    filtered.sort(key=lambda x: -x[1])
    return filtered[:top_k]