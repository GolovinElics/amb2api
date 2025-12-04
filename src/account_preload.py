"""
Account Preload Queue System

后台预加载队列机制，在用户登录后自动预加载所有已登录账户的数据，
并将数据存入缓存，实现账户管理页面的即时数据展示和快速账户切换。

核心组件：
- PreloadTask: 预加载任务数据模型
- PreloadQueueConfig: 队列配置
- AccountDataCache: 账户数据缓存管理器
- AccountPreloadQueue: 预加载队列管理器
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, List, Callable
from collections import OrderedDict

from log import log


class PreloadTaskStatus(str, Enum):
    """预加载任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PreloadDataType(str, Enum):
    """预加载数据类型"""
    OVERVIEW = "overview"      # 账户概览（info + billing + api_keys）
    USAGE = "usage"            # 使用量数据
    COST = "cost"              # 成本数据
    RATES = "rates"            # 费率信息


@dataclass
class PreloadTask:
    """预加载任务"""
    task_id: str
    account_email: str
    data_types: List[str]
    priority: int
    created_at: float
    status: PreloadTaskStatus = PreloadTaskStatus.PENDING
    retry_count: int = 0
    last_error: Optional[str] = None
    
    def __lt__(self, other: "PreloadTask") -> bool:
        """优先级比较，数字越小优先级越高"""
        if self.priority != other.priority:
            return self.priority < other.priority
        # 同优先级按创建时间排序
        return self.created_at < other.created_at
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PreloadTask):
            return False
        return self.task_id == other.task_id
    
    def __hash__(self) -> int:
        return hash(self.task_id)
    
    @classmethod
    def create(
        cls,
        account_email: str,
        data_types: Optional[List[str]] = None,
        priority: int = 0
    ) -> "PreloadTask":
        """创建新的预加载任务"""
        if data_types is None:
            data_types = [dt.value for dt in PreloadDataType]
        return cls(
            task_id=str(uuid.uuid4()),
            account_email=account_email,
            data_types=data_types,
            priority=priority,
            created_at=time.time()
        )


@dataclass
class PreloadQueueConfig:
    """预加载队列配置"""
    max_concurrent: int = 2           # 最大并发数
    refresh_interval: float = 300.0   # 刷新间隔（秒）
    max_queue_size: int = 50          # 队列最大容量
    max_retry: int = 3                # 最大重试次数
    retry_base_delay: float = 1.0     # 重试基础延迟（秒）
    cache_ttl: float = 300.0          # 缓存TTL（秒）
    max_cached_accounts: int = 20     # 最大缓存账户数
    
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "PreloadQueueConfig":
        """从字典创建配置，无效值回退到默认值"""
        defaults = cls()
        
        def safe_int(key: str, min_val: int = 1) -> int:
            try:
                val = int(config.get(key, getattr(defaults, key)))
                return max(min_val, val)
            except (ValueError, TypeError):
                return getattr(defaults, key)
        
        def safe_float(key: str, min_val: float = 0.1) -> float:
            try:
                val = float(config.get(key, getattr(defaults, key)))
                # 检查是否为有效的有限数值
                import math
                if math.isnan(val) or math.isinf(val):
                    return getattr(defaults, key)
                return max(min_val, val)
            except (ValueError, TypeError):
                return getattr(defaults, key)
        
        return cls(
            max_concurrent=safe_int("max_concurrent", 1),
            refresh_interval=safe_float("refresh_interval", 10.0),
            max_queue_size=safe_int("max_queue_size", 1),
            max_retry=safe_int("max_retry", 0),
            retry_base_delay=safe_float("retry_base_delay", 0.1),
            cache_ttl=safe_float("cache_ttl", 10.0),
            max_cached_accounts=safe_int("max_cached_accounts", 1),
        )
    
    def validate(self) -> "PreloadQueueConfig":
        """验证配置值，无效值回退到默认值"""
        defaults = PreloadQueueConfig()
        
        if self.max_concurrent < 1:
            self.max_concurrent = defaults.max_concurrent
        if self.refresh_interval < 10.0:
            self.refresh_interval = defaults.refresh_interval
        if self.max_queue_size < 1:
            self.max_queue_size = defaults.max_queue_size
        if self.max_retry < 0:
            self.max_retry = defaults.max_retry
        if self.retry_base_delay < 0.1:
            self.retry_base_delay = defaults.retry_base_delay
        if self.cache_ttl < 10.0:
            self.cache_ttl = defaults.cache_ttl
        if self.max_cached_accounts < 1:
            self.max_cached_accounts = defaults.max_cached_accounts
        
        return self


@dataclass
class CacheEntry:
    """缓存条目"""
    data: Dict[str, Any]
    timestamp: float
    ttl: float
    access_count: int = 0
    last_access: float = field(default_factory=time.time)
    
    def is_fresh(self) -> bool:
        """检查缓存是否新鲜"""
        return (time.time() - self.timestamp) < self.ttl
    
    def touch(self) -> None:
        """更新访问信息"""
        self.access_count += 1
        self.last_access = time.time()


class AccountDataCache:
    """
    账户数据缓存管理器
    
    封装现有的 _cache_store 机制，添加账户级别的缓存管理，
    支持 LRU 淘汰和登出清理。
    """
    
    def __init__(
        self,
        max_accounts: int = 20,
        default_ttl: float = 300.0
    ):
        """
        初始化缓存管理器
        
        Args:
            max_accounts: 最大缓存账户数
            default_ttl: 默认缓存TTL（秒）
        """
        self._max_accounts = max_accounts
        self._default_ttl = default_ttl
        
        # 账户级别的缓存存储
        # 结构: {account_email: {data_type: CacheEntry}}
        self._cache: Dict[str, Dict[str, CacheEntry]] = {}
        
        # LRU 跟踪：记录账户的最后访问时间
        self._account_access: OrderedDict[str, float] = OrderedDict()
        
        # 并发控制
        self._lock = asyncio.Lock()
    
    async def get_account_data(
        self,
        account_email: str,
        data_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取账户缓存数据
        
        Args:
            account_email: 账户邮箱
            data_type: 数据类型
        
        Returns:
            缓存数据，如果不存在或已过期则返回 None
        """
        async with self._lock:
            account_cache = self._cache.get(account_email)
            if not account_cache:
                return None
            
            entry = account_cache.get(data_type)
            if not entry:
                return None
            
            if not entry.is_fresh():
                # 缓存已过期，删除
                del account_cache[data_type]
                if not account_cache:
                    del self._cache[account_email]
                    if account_email in self._account_access:
                        del self._account_access[account_email]
                return None
            
            # 更新访问信息
            entry.touch()
            self._update_account_access(account_email)
            
            return entry.data
    
    async def set_account_data(
        self,
        account_email: str,
        data_type: str,
        data: Dict[str, Any],
        ttl: Optional[float] = None
    ) -> None:
        """
        设置账户缓存数据
        
        Args:
            account_email: 账户邮箱
            data_type: 数据类型
            data: 要缓存的数据
            ttl: 缓存TTL（秒），默认使用 default_ttl
        """
        async with self._lock:
            # 检查是否需要淘汰
            if account_email not in self._cache:
                await self._evict_if_needed()
            
            # 创建或获取账户缓存
            if account_email not in self._cache:
                self._cache[account_email] = {}
            
            # 创建缓存条目
            entry = CacheEntry(
                data=data,
                timestamp=time.time(),
                ttl=ttl or self._default_ttl
            )
            
            self._cache[account_email][data_type] = entry
            self._update_account_access(account_email)
            
            log.debug(f"Cached {data_type} for {account_email}, ttl={entry.ttl}s")
    
    async def is_fresh(self, account_email: str, data_type: str) -> bool:
        """
        检查缓存是否新鲜
        
        Args:
            account_email: 账户邮箱
            data_type: 数据类型
        
        Returns:
            True 如果缓存存在且新鲜
        """
        async with self._lock:
            account_cache = self._cache.get(account_email)
            if not account_cache:
                return False
            
            entry = account_cache.get(data_type)
            if not entry:
                return False
            
            return entry.is_fresh()
    
    async def get_freshness_info(self, account_email: str) -> Dict[str, Any]:
        """
        获取账户数据新鲜度信息
        
        Args:
            account_email: 账户邮箱
        
        Returns:
            各数据类型的新鲜度信息
        """
        async with self._lock:
            result = {}
            account_cache = self._cache.get(account_email, {})
            
            for data_type in PreloadDataType:
                entry = account_cache.get(data_type.value)
                if entry:
                    result[data_type.value] = {
                        "cached": True,
                        "fresh": entry.is_fresh(),
                        "cached_at": entry.timestamp,
                        "ttl": entry.ttl,
                        "age": time.time() - entry.timestamp,
                        "access_count": entry.access_count,
                    }
                else:
                    result[data_type.value] = {
                        "cached": False,
                        "fresh": False,
                    }
            
            return result
    
    async def clear_account(self, account_email: str) -> None:
        """
        清除指定账户的所有缓存
        
        Args:
            account_email: 账户邮箱
        """
        async with self._lock:
            if account_email in self._cache:
                del self._cache[account_email]
                log.info(f"Cleared cache for account {account_email}")
            
            if account_email in self._account_access:
                del self._account_access[account_email]
    
    async def clear_all(self) -> None:
        """清除所有缓存"""
        async with self._lock:
            self._cache.clear()
            self._account_access.clear()
            log.info("Cleared all account cache")
    
    def _update_account_access(self, account_email: str) -> None:
        """更新账户访问时间（内部方法，需在锁内调用）"""
        # 移动到末尾（最近访问）
        if account_email in self._account_access:
            self._account_access.move_to_end(account_email)
        self._account_access[account_email] = time.time()
    
    async def _evict_if_needed(self) -> None:
        """如果超过最大账户数，淘汰最少使用的账户（内部方法，需在锁内调用）"""
        while len(self._cache) >= self._max_accounts:
            await self._evict_lru()
    
    async def _evict_lru(self) -> None:
        """淘汰最近最少使用的账户缓存（内部方法，需在锁内调用）"""
        if not self._account_access:
            return
        
        # 获取最早访问的账户（OrderedDict 的第一个）
        lru_account = next(iter(self._account_access))
        
        if lru_account in self._cache:
            del self._cache[lru_account]
            log.info(f"Evicted LRU cache for account {lru_account}")
        
        del self._account_access[lru_account]
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_entries = sum(len(cache) for cache in self._cache.values())
        return {
            "cached_accounts": len(self._cache),
            "max_accounts": self._max_accounts,
            "total_entries": total_entries,
            "default_ttl": self._default_ttl,
        }



class AccountPreloadQueue:
    """
    账户数据预加载队列管理器
    
    管理预加载任务的优先级和执行，支持：
    - 优先级队列（当前账户优先）
    - 并发控制
    - 动态重排序
    - 定时刷新
    - 错误重试
    """
    
    def __init__(
        self,
        config: Optional[PreloadQueueConfig] = None,
        cache: Optional[AccountDataCache] = None,
        fetch_func: Optional[Callable] = None
    ):
        """
        初始化预加载队列
        
        Args:
            config: 队列配置
            cache: 账户数据缓存
            fetch_func: 数据获取函数，签名: async (account_email, data_type) -> Dict
        """
        self._config = config or PreloadQueueConfig()
        self._cache = cache or AccountDataCache(
            max_accounts=self._config.max_cached_accounts,
            default_ttl=self._config.cache_ttl
        )
        self._fetch_func = fetch_func
        
        # 任务队列
        self._queue: List[PreloadTask] = []
        self._running_tasks: Dict[str, PreloadTask] = {}  # task_id -> task
        
        # 并发控制
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._queue_lock = asyncio.Lock()
        
        # 工作协程
        self._worker_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # 状态
        self._started = False
        self._current_account: Optional[str] = None
        
        # 统计
        self._stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }
    
    async def start(self) -> None:
        """启动队列处理和定时刷新"""
        if self._started:
            return
        
        self._shutdown_event.clear()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent)
        
        # 使用 TaskManager 注册任务
        from .task_manager import task_manager
        
        self._worker_task = task_manager.create_task(
            self._process_queue(),
            name="account_preload_worker"
        )
        
        self._scheduler_task = task_manager.create_task(
            self._refresh_scheduler(),
            name="account_preload_scheduler"
        )
        
        self._started = True
        log.info("AccountPreloadQueue started")
    
    async def stop(self) -> None:
        """停止队列处理，清理资源"""
        if not self._started:
            return
        
        self._shutdown_event.set()
        
        # 等待工作协程结束
        if self._worker_task and not self._worker_task.done():
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()
        
        if self._scheduler_task and not self._scheduler_task.done():
            try:
                await asyncio.wait_for(self._scheduler_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._scheduler_task.cancel()
        
        self._started = False
        log.info("AccountPreloadQueue stopped")
    
    async def enqueue_account(
        self,
        account_email: str,
        priority: int = 0,
        data_types: Optional[List[str]] = None
    ) -> str:
        """
        将账户加入预加载队列
        
        Args:
            account_email: 账户邮箱
            priority: 优先级（数字越小优先级越高，0为最高）
            data_types: 要加载的数据类型列表
        
        Returns:
            任务ID
        """
        async with self._queue_lock:
            # 检查是否已有该账户的任务
            existing = next(
                (t for t in self._queue if t.account_email == account_email),
                None
            )
            if existing:
                # 如果新优先级更高，更新优先级
                if priority < existing.priority:
                    existing.priority = priority
                    self._queue.sort()
                return existing.task_id
            
            # 检查队列是否已满
            if len(self._queue) >= self._config.max_queue_size:
                # 移除最低优先级的任务
                self._queue.sort()
                removed = self._queue.pop()
                log.warning(f"Queue full, removed task: {removed.task_id}")
            
            # 创建新任务
            task = PreloadTask.create(
                account_email=account_email,
                data_types=data_types,
                priority=priority
            )
            
            self._queue.append(task)
            self._queue.sort()
            
            log.debug(f"Enqueued preload task for {account_email}, priority={priority}")
            return task.task_id
    
    async def enqueue_all_accounts(
        self,
        current_account: Optional[str] = None,
        accounts: Optional[List[str]] = None
    ) -> List[str]:
        """
        将所有已登录账户加入队列，当前账户优先
        
        Args:
            current_account: 当前选中的账户邮箱
            accounts: 账户列表，如果为None则从存储获取
        
        Returns:
            任务ID列表
        """
        self._current_account = current_account
        
        if accounts is None:
            # 从存储获取账户列表
            from .storage_adapter import get_storage_adapter
            adapter = await get_storage_adapter()
            accounts_data = await adapter.get_config("assembly_accounts_list")
            log.debug(f"[Preload] Got accounts_data from storage: {accounts_data}")
            if accounts_data and isinstance(accounts_data, list):
                accounts = [acc.get("email") for acc in accounts_data if acc.get("email")]
            else:
                accounts = []
        
        log.info(f"[Preload] enqueue_all_accounts: current={current_account}, accounts={accounts}")
        
        task_ids = []
        
        # 当前账户优先级0（即使不在 accounts 列表中也要加入）
        if current_account:
            task_id = await self.enqueue_account(current_account, priority=0)
            task_ids.append(task_id)
            log.info(f"[Preload] Enqueued current account {current_account} with priority 0")
        
        # 其他账户优先级1+
        for i, email in enumerate(accounts):
            if email != current_account:
                task_id = await self.enqueue_account(email, priority=i + 1)
                task_ids.append(task_id)
                log.debug(f"[Preload] Enqueued account {email} with priority {i + 1}")
        
        log.info(f"[Preload] Enqueued {len(task_ids)} accounts for preloading")
        return task_ids
    
    async def reprioritize(self, account_email: str) -> None:
        """
        将指定账户提升到最高优先级
        
        Args:
            account_email: 要提升优先级的账户邮箱
        """
        async with self._queue_lock:
            self._current_account = account_email
            
            # 查找该账户的任务
            task = next(
                (t for t in self._queue if t.account_email == account_email),
                None
            )
            
            if task:
                # 将所有其他任务的优先级+1
                for t in self._queue:
                    if t.account_email != account_email:
                        t.priority += 1
                
                # 将目标任务优先级设为0
                task.priority = 0
                self._queue.sort()
                
                log.info(f"Reprioritized {account_email} to top of queue")
            else:
                # 如果不在队列中，直接添加到队首（不调用 enqueue_account 避免死锁）
                new_task = PreloadTask.create(
                    account_email=account_email,
                    priority=0
                )
                self._queue.insert(0, new_task)
                log.info(f"Added {account_email} to top of queue")
    
    async def cancel_account(self, account_email: str) -> bool:
        """
        取消指定账户的待处理任务
        
        Args:
            account_email: 账户邮箱
        
        Returns:
            是否成功取消
        """
        async with self._queue_lock:
            original_len = len(self._queue)
            self._queue = [t for t in self._queue if t.account_email != account_email]
            cancelled = original_len - len(self._queue)
            
            if cancelled > 0:
                log.info(f"Cancelled {cancelled} tasks for {account_email}")
                return True
            return False
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态信息"""
        return {
            "started": self._started,
            "queue_size": len(self._queue),
            "running_tasks": len(self._running_tasks),
            "current_account": self._current_account,
            "config": {
                "max_concurrent": self._config.max_concurrent,
                "refresh_interval": self._config.refresh_interval,
                "max_queue_size": self._config.max_queue_size,
            },
            "stats": self._stats.copy(),
            "cache_stats": self._cache.get_stats(),
        }
    
    async def _process_queue(self) -> None:
        """队列处理工作协程"""
        while not self._shutdown_event.is_set():
            try:
                # 获取下一个任务
                task = await self._get_next_task()
                if not task:
                    # 队列为空，等待一段时间
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=1.0
                        )
                        break
                    except asyncio.TimeoutError:
                        continue
                
                # 使用信号量控制并发
                async with self._semaphore:
                    await self._execute_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in preload queue worker: {e}")
                await asyncio.sleep(1)
    
    async def _get_next_task(self) -> Optional[PreloadTask]:
        """获取下一个待处理任务"""
        async with self._queue_lock:
            if not self._queue:
                return None
            
            # 获取优先级最高的任务
            task = self._queue.pop(0)
            task.status = PreloadTaskStatus.RUNNING
            self._running_tasks[task.task_id] = task
            return task
    
    async def _execute_task(self, task: PreloadTask) -> None:
        """执行预加载任务"""
        try:
            log.debug(f"Executing preload task for {task.account_email}")
            
            for data_type in task.data_types:
                try:
                    # 检查缓存是否新鲜
                    if await self._cache.is_fresh(task.account_email, data_type):
                        self._stats["cache_hits"] += 1
                        continue
                    
                    self._stats["cache_misses"] += 1
                    
                    # 获取数据
                    if self._fetch_func:
                        data = await self._fetch_func(task.account_email, data_type)
                        if data:
                            await self._cache.set_account_data(
                                task.account_email,
                                data_type,
                                data
                            )
                    
                except Exception as e:
                    log.warning(f"Failed to fetch {data_type} for {task.account_email}: {e}")
            
            task.status = PreloadTaskStatus.COMPLETED
            self._stats["tasks_completed"] += 1
            log.debug(f"Completed preload task for {task.account_email}")
            
        except Exception as e:
            task.status = PreloadTaskStatus.FAILED
            task.last_error = str(e)
            task.retry_count += 1
            self._stats["tasks_failed"] += 1
            
            # 重试逻辑
            if task.retry_count < self._config.max_retry:
                delay = self._config.retry_base_delay * (2 ** task.retry_count)
                log.warning(f"Task failed, retry {task.retry_count}/{self._config.max_retry} after {delay}s: {e}")
                
                await asyncio.sleep(delay)
                
                async with self._queue_lock:
                    task.status = PreloadTaskStatus.PENDING
                    self._queue.append(task)
                    self._queue.sort()
            else:
                log.error(f"Task failed after {self._config.max_retry} retries: {e}")
        
        finally:
            # 从运行中任务移除
            self._running_tasks.pop(task.task_id, None)
    
    async def _refresh_scheduler(self) -> None:
        """定时刷新调度器"""
        while not self._shutdown_event.is_set():
            try:
                # 等待刷新间隔
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self._config.refresh_interval
                )
                break  # 收到关闭信号
            except asyncio.TimeoutError:
                # 触发刷新
                log.debug("Triggering scheduled refresh")
                await self.enqueue_all_accounts(current_account=self._current_account)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Error in refresh scheduler: {e}")
                await asyncio.sleep(10)
    
    @property
    def cache(self) -> AccountDataCache:
        """获取缓存实例"""
        return self._cache


# 全局预加载队列实例
_preload_queue: Optional[AccountPreloadQueue] = None


async def _default_fetch_func(account_email: str, data_type: str) -> Optional[Dict[str, Any]]:
    """
    默认的数据获取函数，调用现有的 account_api 接口获取数据
    
    Args:
        account_email: 账户邮箱
        data_type: 数据类型 (overview, usage, cost, rates)
    
    Returns:
        获取到的数据，失败返回 None
    """
    try:
        # 延迟导入避免循环依赖
        from . import account_api
        
        log.info(f"[Preload] Fetching {data_type} for {account_email}")
        
        if data_type == PreloadDataType.OVERVIEW.value:
            # 调用 overview 接口获取合并数据（info + billing + api_keys）
            result = await account_api.get_account_overview(
                force=True,  # 强制刷新，不使用缓存
                account_email=account_email
            )
            log.info(f"[Preload] Fetched overview for {account_email}: {list(result.keys()) if result else 'None'}")
            return result
            
        elif data_type == PreloadDataType.USAGE.value:
            # 调用 usage 接口
            result = await account_api.get_usage_data(
                force=True,
                account_email=account_email
            )
            log.info(f"[Preload] Fetched usage for {account_email}")
            return result
            
        elif data_type == PreloadDataType.COST.value:
            # 调用内部 cost 接口（不需要 Request 对象）
            result = await account_api._fetch_cost_data_internal(
                account_email=account_email,
                force=True
            )
            log.info(f"[Preload] Fetched cost for {account_email}")
            return result
            
        elif data_type == PreloadDataType.RATES.value:
            # 调用 rates 接口
            result = await account_api.get_rates(
                force=True,
                account_email=account_email
            )
            log.info(f"[Preload] Fetched rates for {account_email}")
            return result
        
        log.warning(f"[Preload] Unknown data type: {data_type}")
        return None
        
    except Exception as e:
        log.warning(f"[Preload] Failed to fetch {data_type} for {account_email}: {e}")
        import traceback
        log.debug(f"[Preload] Traceback: {traceback.format_exc()}")
        return None


async def get_preload_queue() -> AccountPreloadQueue:
    """获取全局预加载队列实例"""
    global _preload_queue
    
    if _preload_queue is None:
        # 从配置加载队列参数
        try:
            from config import get_preload_config
            config_dict = await get_preload_config()
            config = PreloadQueueConfig.from_dict(config_dict)
        except Exception as e:
            log.warning(f"Failed to load preload config, using defaults: {e}")
            config = PreloadQueueConfig()
        
        _preload_queue = AccountPreloadQueue(
            config=config,
            fetch_func=_default_fetch_func
        )
        log.info(f"[Preload] Created preload queue with config: max_concurrent={config.max_concurrent}, refresh_interval={config.refresh_interval}")
    
    return _preload_queue


async def start_preload_queue() -> AccountPreloadQueue:
    """启动全局预加载队列"""
    queue = await get_preload_queue()
    await queue.start()
    return queue


async def stop_preload_queue() -> None:
    """停止全局预加载队列"""
    global _preload_queue
    
    if _preload_queue:
        await _preload_queue.stop()
        _preload_queue = None
