"""
节点层：每个节点负责一小步逻辑

包含以下节点：
- input_node: 输入预处理
- emotion_node: 情绪识别
- retrieval_node: BM25检索
- character_node: 角色装配
- strategy_node: 多轮对话策略规划
- generation_node: 回复生成
- negotiation_node: 协商占位
- logging_node: 日志记录
- evaluation_nodes: 评估节点
"""

from .strategy_node import strategy_node