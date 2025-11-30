"""
统一统计模块
整合所有统计数据源，确保总调用数与详情统计保持一致

设计原则：
1. 使用脱敏密钥 (masked_key) 作为统一的标识符
2. 所有统计数据存储在一个地方
3. 当密钥被删除时，同步删除其统计数据
"""
import time
import asyncio
import hashlib
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

from log import log
from .storage_adapter import get_storage_adapter


def _get_next_utc_7am() -> datetime:
    """计算下一个 UTC 07:00 时间用于配额重置"""
    now = datetime.now(timezone.utc)
    today_7am = now.replace(hour=7, minute=0, second=0, microsecond=0)
    
    if now < today_7am:
        return today_7am
    else:
        return today_7am + timedelta(days=1)


def mask_key(key: str) -> str:
    """
    脱敏密钥，与 assembly_client.py 中的 _mask_key 保持一致
    """
    if not key:
        return ""
    k = str(key)
    if len(k) <= 8:
        return k[:2] + "***"
    return k[:4] + "..." + k[-4:]


def get_key_hash(key: str) -> str:
    """获取密钥的哈希值（用于存储）"""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]


class UnifiedStats:
    """
    统一统计管理器
    
    数据结构：
    {
        "masked_key": {
            "full_key_hash": "xxx",  # 完整密钥的哈希，用于验证
            "success_count": 0,
            "failure_count": 0,
            "model_counts": {"model_name": count},
            "last_call_time": timestamp,
            "created_time": timestamp,
        }
    }
    """
    
    def __init__(self):
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._initialized = False
        self._save_lock = asyncio.Lock()
        self._dirty = False
        self._last_save_time = 0
        self._save_interval = 30  # 保存间隔（秒）
    
    async def initialize(self):
        """初始化统计管理器"""
        if self._initialized:
            return
        await self._load_stats()
        self._initialized = True
        log.info(f"UnifiedStats initialized with {len(self._stats)} keys")
    
    async def _load_stats(self):
        """从存储加载统计数据"""
        try:
            adapter = await get_storage_adapter()
            data = await adapter.get_config("unified_stats", {})
            
            if isinstance(data, dict):
                self._stats = data
            
            log.debug(f"Loaded unified stats for {len(self._stats)} keys")
        except Exception as e:
            log.error(f"Failed to load unified stats: {e}")
    
    async def _save_stats(self, force: bool = False):
        """保存统计数据到存储"""
        current_time = time.time()
        
        if not force and not self._dirty:
            return
        if not force and current_time - self._last_save_time < self._save_interval:
            return
        
        async with self._save_lock:
            try:
                adapter = await get_storage_adapter()
                await adapter.set_config("unified_stats", self._stats)
                self._dirty = False
                self._last_save_time = current_time
                log.debug(f"Saved unified stats for {len(self._stats)} keys")
            except Exception as e:
                log.error(f"Failed to save unified stats: {e}")
    
    async def record_call(
        self,
        api_key: str,
        model: str,
        success: bool,
    ):
        """
        记录 API 调用
        
        Args:
            api_key: 完整的 API 密钥
            model: 模型名称
            success: 是否成功
        """
        if not self._initialized:
            await self.initialize()
        
        masked = mask_key(api_key)
        key_hash = get_key_hash(api_key)
        
        if masked not in self._stats:
            self._stats[masked] = {
                "full_key_hash": key_hash,
                "success_count": 0,
                "failure_count": 0,
                "model_counts": {},
                "last_call_time": 0,
                "created_time": time.time(),
            }
        
        stats = self._stats[masked]
        
        if success:
            stats["success_count"] = stats.get("success_count", 0) + 1
        else:
            stats["failure_count"] = stats.get("failure_count", 0) + 1
        
        # 更新模型计数（区分成功和失败）
        model_counts = stats.get("model_counts", {})
        if model not in model_counts:
            model_counts[model] = {"ok": 0, "fail": 0}
        # 兼容旧格式（如果是数字则转换为新格式）
        if isinstance(model_counts.get(model), int):
            old_count = model_counts[model]
            model_counts[model] = {"ok": old_count, "fail": 0}
        
        if success:
            model_counts[model]["ok"] = model_counts[model].get("ok", 0) + 1
        else:
            model_counts[model]["fail"] = model_counts[model].get("fail", 0) + 1
        stats["model_counts"] = model_counts
        
        # 更新最后调用时间
        stats["last_call_time"] = time.time()
        
        self._dirty = True
        
        log.debug(f"Recorded {'success' if success else 'failure'} call for key {masked}, model={model}")
        
        # 异步保存
        asyncio.create_task(self._save_stats())
    
    async def get_stats_for_key(self, masked_key: str) -> Dict[str, Any]:
        """获取单个密钥的统计信息"""
        if not self._initialized:
            await self.initialize()
        
        stats = self._stats.get(masked_key, {})
        return {
            "masked_key": masked_key,
            "success_count": stats.get("success_count", 0),
            "failure_count": stats.get("failure_count", 0),
            "total_calls": stats.get("success_count", 0) + stats.get("failure_count", 0),
            "model_counts": stats.get("model_counts", {}),
            "last_call_time": stats.get("last_call_time", 0),
        }
    
    async def get_all_stats(self, valid_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        获取所有统计信息
        
        Args:
            valid_keys: 有效密钥列表（完整密钥），如果提供则只返回这些密钥的统计
        
        Returns:
            统计信息字典
        """
        if not self._initialized:
            await self.initialize()
        
        # 如果提供了有效密钥列表，构建脱敏密钥集合
        valid_masked_keys = None
        if valid_keys is not None:
            valid_masked_keys = {mask_key(k) for k in valid_keys}
        
        result = {
            "keys": {},
            "total": {
                "success": 0,
                "failure": 0,
                "total_calls": 0,
            },
            "models": {},
        }
        
        for masked_key, stats in self._stats.items():
            # 如果提供了有效密钥列表，只统计有效密钥
            if valid_masked_keys is not None and masked_key not in valid_masked_keys:
                continue
            
            success = stats.get("success_count", 0)
            failure = stats.get("failure_count", 0)
            total = success + failure
            
            # 处理 model_counts（兼容新旧格式）
            model_counts_raw = stats.get("model_counts", {})
            model_counts_display = {}  # 用于显示的格式
            models_detail = {}  # 详细的成功/失败信息
            
            for model, count_data in model_counts_raw.items():
                if isinstance(count_data, int):
                    # 旧格式：只有总数
                    model_counts_display[model] = count_data
                    models_detail[model] = {"ok": count_data, "fail": 0}
                elif isinstance(count_data, dict):
                    # 新格式：区分成功失败
                    ok = count_data.get("ok", 0)
                    fail = count_data.get("fail", 0)
                    model_counts_display[model] = ok + fail
                    models_detail[model] = {"ok": ok, "fail": fail}
            
            result["keys"][masked_key] = {
                "ok": success,
                "fail": failure,
                "total": total,
                "model_counts": model_counts_display,
                "models": models_detail,
            }
            
            # 累加总数
            result["total"]["success"] += success
            result["total"]["failure"] += failure
            result["total"]["total_calls"] += total
            
            # 累加模型统计
            for model, detail in models_detail.items():
                if model not in result["models"]:
                    result["models"][model] = {"ok": 0, "fail": 0}
                result["models"][model]["ok"] += detail["ok"]
                result["models"][model]["fail"] += detail["fail"]
        
        return result
    
    async def delete_stats_for_key(self, api_key: str) -> bool:
        """
        删除指定密钥的统计数据
        
        Args:
            api_key: 完整的 API 密钥
        
        Returns:
            是否成功删除
        """
        if not self._initialized:
            await self.initialize()
        
        masked = mask_key(api_key)
        
        if masked in self._stats:
            del self._stats[masked]
            self._dirty = True
            await self._save_stats(force=True)
            log.info(f"Deleted stats for key {masked}")
            return True
        
        return False
    
    async def delete_stats_for_masked_key(self, masked_key: str) -> bool:
        """
        删除指定脱敏密钥的统计数据
        
        Args:
            masked_key: 脱敏后的密钥
        
        Returns:
            是否成功删除
        """
        if not self._initialized:
            await self.initialize()
        
        if masked_key in self._stats:
            del self._stats[masked_key]
            self._dirty = True
            await self._save_stats(force=True)
            log.info(f"Deleted stats for masked key {masked_key}")
            return True
        
        return False
    
    async def cleanup_invalid_keys(self, valid_keys: List[str]) -> int:
        """
        清理无效密钥的统计数据
        
        Args:
            valid_keys: 有效密钥列表（完整密钥）
        
        Returns:
            删除的统计数量
        """
        if not self._initialized:
            await self.initialize()
        
        valid_masked_keys = {mask_key(k) for k in valid_keys}
        
        # 找出需要删除的统计
        to_delete = [k for k in self._stats.keys() if k not in valid_masked_keys]
        
        for masked_key in to_delete:
            del self._stats[masked_key]
        
        if to_delete:
            self._dirty = True
            await self._save_stats(force=True)
            log.info(f"Cleaned up stats for {len(to_delete)} invalid keys: {to_delete}")
        
        return len(to_delete)
    
    async def reset_stats(self, masked_key: Optional[str] = None):
        """
        重置统计数据
        
        Args:
            masked_key: 脱敏密钥，如果为 None 则重置所有
        """
        if not self._initialized:
            await self.initialize()
        
        if masked_key is not None:
            if masked_key in self._stats:
                self._stats[masked_key] = {
                    "full_key_hash": self._stats[masked_key].get("full_key_hash", ""),
                    "success_count": 0,
                    "failure_count": 0,
                    "model_counts": {},
                    "last_call_time": 0,
                    "created_time": self._stats[masked_key].get("created_time", time.time()),
                }
                log.info(f"Reset stats for key {masked_key}")
        else:
            for key in self._stats:
                self._stats[key] = {
                    "full_key_hash": self._stats[key].get("full_key_hash", ""),
                    "success_count": 0,
                    "failure_count": 0,
                    "model_counts": {},
                    "last_call_time": 0,
                    "created_time": self._stats[key].get("created_time", time.time()),
                }
            log.info("Reset all stats")
        
        self._dirty = True
        await self._save_stats(force=True)
    
    async def ensure_keys_exist(self, keys: List[str]):
        """
        确保指定的密钥在统计中存在（即使没有调用记录）
        
        Args:
            keys: 完整密钥列表
        """
        if not self._initialized:
            await self.initialize()
        
        for key in keys:
            masked = mask_key(key)
            if masked not in self._stats:
                self._stats[masked] = {
                    "full_key_hash": get_key_hash(key),
                    "success_count": 0,
                    "failure_count": 0,
                    "model_counts": {},
                    "last_call_time": 0,
                    "created_time": time.time(),
                }
                self._dirty = True
        
        if self._dirty:
            await self._save_stats()


# 全局实例
_unified_stats: Optional[UnifiedStats] = None


async def get_unified_stats() -> UnifiedStats:
    """获取全局统一统计实例"""
    global _unified_stats
    if _unified_stats is None:
        _unified_stats = UnifiedStats()
        await _unified_stats.initialize()
    return _unified_stats
