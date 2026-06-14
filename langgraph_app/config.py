import os

# 以当前文件为基准动态推断项目根目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)

# ========= 数据路径（根据你现有项目结构） =========

# 角色风格与支持策略：character_get_fengge_style_support_seven.json
STYLE_SUPPORT_PATH = os.path.join(
    PROJECT_ROOT,
    "character_get_fengge_style_support_seven.json"
)

# 角色 MBTI 数据：data/character_mbti.json
CHARACTER_MBTI_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "character_mbti.json"
)

# 角色画像数据库：data/character_profiles_bank.json
CHARACTER_PROFILES_BANK_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "character_profiles_bank.json"
)

# 角色详细资料：
# 优先 data/character_profiles_mbti.json，没有则退回根目录 character_profiles.json
CHARACTER_PROFILES_MBTI_PATH = os.path.join(
    PROJECT_ROOT,
    "data",
    "character_profiles_mbti.json"
)
CHARACTER_PROFILES_FALLBACK_PATH = os.path.join(
    PROJECT_ROOT,
    "character_profiles.json"
)

# BM25 模块路径
BM25_MODULE_PATH = os.path.join(
    PROJECT_ROOT,
    "BM25"
)

# ========= 模型与默认配置 =========

# 默认 LLM 名称（要和 utils.functions.call_llm 里支持的名字一致）
# 你在代码里大量使用 "gpt-3.5-turbo" / "gpt-4o" / "deepseek-r1" 等，这里选一个作为主对话模型
DEFAULT_AGENT_LLM = "gpt-3.5-turbo"

# 默认检索方法（如果后续用到 get_response_NEW 里的 retrieval_method，可以对齐）
DEFAULT_RETRIEVAL_METHOD = "C-A_context"

from typing import Optional

def load_first_existing(*paths: str) -> Optional[str]:
    """返回第一个存在的路径，不存在则返回 None"""
    for p in paths:
        if os.path.exists(p):
            return p
    return None