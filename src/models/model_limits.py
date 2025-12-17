"""
模型限制信息管理模块

提供模型 max_completion_tokens 的获取和缓存功能
"""

import asyncio
import time
import logging
from typing import Dict, Any, Optional

log = logging.getLogger("amb2api")

# 模型 max_completion_tokens 的默认值（作为 fallback）
DEFAULT_MODEL_LIMITS: Dict[str, int] = {
    # GPT 系列
    "gpt-5": 16384,
    "gpt-5-mini": 16384,
    "gpt-5-nano": 8192,
    "gpt-4.1": 32768,
    "gpt-4.1-mini": 16384,
    "gpt-4.1-nano": 8192,
    "gpt-oss-120b": 8192,
    "gpt-oss-20b": 8192,
    "chatgpt-4o": 16384,
    # Claude 系列
    "claude-4-opus": 8192,
    "claude-4.5-sonnet": 8192,
    "claude-4-sonnet": 8192,
    "claude-4.5-haiku": 8192,
    "claude-3.5-haiku": 8192,
    "claude-3-haiku": 4096,
    # Gemini 系列
    "gemini-3-pro": 65536,
    "gemini-2.5-pro": 65536,
    "gemini-2.5-flash": 65536,
    "gemini-2.5-flash-lite": 32768,
}

# 未知模型的默认 max_tokens
DEFAULT_MAX_TOKENS = 8192

# 缓存配置
_model_limits_cache: Dict[str, int] = {}
_cache_timestamp: float = 0
_cache_ttl: float = 300  # 5分钟缓存


async def _fetch_model_limits_from_api() -> Dict[str, int]:
    """
    从 /v1/models API 获取模型限制信息
    """
    try:
        from .assembly_client import fetch_assembly_models
        
        result = await fetch_assembly_models()
        meta = result.get("meta", {})
        
        limits = {}
        for model_id, model_meta in meta.items():
            max_tokens = model_meta.get("max_tokens")
            if max_tokens and isinstance(max_tokens, int) and max_tokens > 0:
                limits[model_id.lower()] = max_tokens
                
        log.debug(f"Fetched model limits from API: {len(limits)} models")
        return limits
        
    except Exception as e:
        log.warning(f"Failed to fetch model limits from API: {e}")
        return {}


def _normalize_model_id(model_id: str) -> str:
    """
    标准化模型 ID（小写，处理别名）
    """
    normalized = model_id.lower().strip()
    
    # 模型别名映射
    aliases = {
        "chatgpt-4o-latest": "chatgpt-4o",
        "chatgpt 4o latest": "chatgpt-4o",
        "gpt 5": "gpt-5",
        "gpt 5 mini": "gpt-5-mini",
        "gpt 5 nano": "gpt-5-nano",
        "claude 4 opus": "claude-4-opus",
        "claude 4.5 sonnet": "claude-4.5-sonnet",
        "claude 4 sonnet": "claude-4-sonnet",
        "claude 4.5 haiku": "claude-4.5-haiku",
        "claude 3.5 haiku": "claude-3.5-haiku",
        "claude 3 haiku": "claude-3-haiku",
        "gemini 3 pro": "gemini-3-pro",
        "gemini 2.5 pro": "gemini-2.5-pro",
        "gemini 2.5 flash": "gemini-2.5-flash",
        "gemini 2.5 flash lite": "gemini-2.5-flash-lite",
    }
    
    # 替换空格为连字符
    normalized = normalized.replace(" ", "-").replace("_", "-")
    
    return aliases.get(normalized, normalized)


async def refresh_model_limits_cache() -> None:
    """
    刷新模型限制缓存
    """
    global _model_limits_cache, _cache_timestamp
    
    api_limits = await _fetch_model_limits_from_api()
    
    # 合并 API 数据和默认值
    _model_limits_cache = dict(DEFAULT_MODEL_LIMITS)
    _model_limits_cache.update(api_limits)
    _cache_timestamp = time.time()
    
    log.info(f"Model limits cache refreshed: {len(_model_limits_cache)} models")


async def get_model_max_tokens(model_id: str) -> int:
    """
    获取指定模型的 max_completion_tokens
    
    Args:
        model_id: 模型 ID
        
    Returns:
        模型的 max_completion_tokens，如果未知则返回默认值
    """
    global _model_limits_cache, _cache_timestamp
    
    # 检查缓存是否过期
    if time.time() - _cache_timestamp > _cache_ttl:
        await refresh_model_limits_cache()
    
    # 标准化模型 ID
    normalized = _normalize_model_id(model_id)
    
    # 查找缓存
    if normalized in _model_limits_cache:
        return _model_limits_cache[normalized]
    
    # 尝试模糊匹配（部分匹配）
    for cached_model, limit in _model_limits_cache.items():
        if normalized in cached_model or cached_model in normalized:
            log.debug(f"Fuzzy match: {model_id} -> {cached_model} = {limit}")
            return limit
    
    log.debug(f"Model {model_id} not found in cache, using default {DEFAULT_MAX_TOKENS}")
    return DEFAULT_MAX_TOKENS


def get_model_max_tokens_sync(model_id: str) -> int:
    """
    同步版本的 get_model_max_tokens（不刷新缓存）
    """
    normalized = _normalize_model_id(model_id)
    
    if normalized in _model_limits_cache:
        return _model_limits_cache[normalized]
    
    if normalized in DEFAULT_MODEL_LIMITS:
        return DEFAULT_MODEL_LIMITS[normalized]
    
    return DEFAULT_MAX_TOKENS
