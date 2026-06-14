from typing import List
from dataclasses import dataclass


@dataclass
class RAGFlowChunk:
    content: str
    score: float
    metadata: dict


class RAGFlowClient:
    """
    当前你没有部署 RAGFlow，这里只是一个占位实现。
    对话主流程不会调用它，不会影响运行。
    """

    def __init__(self, base_url: str = "http://localhost:9380", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def retrieve(self, dataset_name: str, query: str, top_k: int = 5) -> List[RAGFlowChunk]:
        # TODO: 如果以后你部署了 RAGFlow，可以在这里实现真实检索逻辑
        return []