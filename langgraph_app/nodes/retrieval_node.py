from typing import List

from ..state import ConversationState
from ..services.bm25_service import bm25_retrieve


def retrieval_node(state: ConversationState) -> ConversationState:
    """
    检索节点：
    - 使用 BM25 对用户问题做检索
    - 🔧 改进：添加错误处理和调试信息
    """
    query = (state.get("user_query") or "").strip()
    
    if not query:
        print(f"⚠️ [retrieval_node] 用户问题为空，跳过检索")
        state["retrieved_memory"] = []
        state["retrieval_debug"] = {
            "bm25_top_k": 0,
            "error": "用户问题为空"
        }
        return state
    
    try:
        print(f"🔍 [retrieval_node] 开始检索，查询: {query[:100]}...")
        
        # 调用 BM25 检索
        results = bm25_retrieve(query, top_k=10)
        
        # 提取文档内容
        docs: List[str] = []
        scores: List[float] = []
        
        for doc, score in results:
            if doc and isinstance(doc, str) and doc.strip():
                docs.append(doc.strip())
                scores.append(score)
        
        print(f"✅ [retrieval_node] 检索完成，找到 {len(docs)} 条相关记忆")
        
        # 显示前3条结果的预览
        if docs:
            print(f"🔍 [retrieval_node] 前3条记忆预览:")
            for i, doc in enumerate(docs[:3]):
                print(f"   {i+1}. {doc[:100]}...")
        
        # 存储检索结果
        state["retrieved_memory"] = docs
        state["retrieval_scores"] = scores  # 可选：存储相似度分数
        state["retrieval_debug"] = {
            "bm25_top_k": len(docs),
            "query": query[:100],  # 存储查询内容（截断）
            "has_results": len(docs) > 0,
            "error": None
        }
        
    except Exception as e:
        print(f"❌ [retrieval_node] 检索失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # 错误时返回空结果
        state["retrieved_memory"] = []
        state["retrieval_scores"] = []
        state["retrieval_debug"] = {
            "bm25_top_k": 0,
            "query": query[:100],
            "has_results": False,
            "error": str(e)
        }
    
    return state