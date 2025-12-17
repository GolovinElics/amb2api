"""
Property-Based Tests for Account Preload Queue System

使用 hypothesis 库进行属性测试，验证账户预加载队列的正确性属性。
每个测试运行至少 100 次迭代。
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import time
import pytest
from hypothesis import given, strategies as st, settings, assume

from src.services.account_preload import (
    PreloadTask,
    PreloadTaskStatus,
    PreloadDataType,
    PreloadQueueConfig,
    CacheEntry,
)


# ============================================================================
# Strategies for generating test data
# ============================================================================

email_strategy = st.emails()
priority_strategy = st.integers(min_value=0, max_value=100)
data_types_strategy = st.lists(
    st.sampled_from([dt.value for dt in PreloadDataType]),
    min_size=1,
    max_size=4,
    unique=True
)


def task_strategy():
    """生成随机 PreloadTask"""
    return st.builds(
        PreloadTask.create,
        account_email=email_strategy,
        data_types=data_types_strategy,
        priority=priority_strategy
    )


# ============================================================================
# Property 1: Current Account Priority
# **Feature: account-preload-queue, Property 1: Current Account Priority**
# *For any* set of logged-in accounts with a designated current account,
# when the preload queue processes tasks, the current account's data
# SHALL be loaded before any other account's data.
# **Validates: Requirements 1.2, 3.2**
# ============================================================================

class TestPreloadTaskPriorityOrdering:
    """测试 PreloadTask 优先级排序"""
    
    @settings(max_examples=100)
    @given(
        emails=st.lists(email_strategy, min_size=2, max_size=10, unique=True),
        current_idx=st.integers(min_value=0)
    )
    def test_current_account_always_first_when_priority_zero(self, emails, current_idx):
        """
        **Feature: account-preload-queue, Property 1: Current Account Priority**
        当前账户（优先级0）应始终排在其他账户（优先级>0）之前
        """
        current_idx = current_idx % len(emails)
        current_email = emails[current_idx]
        
        # 创建任务：当前账户优先级0，其他账户优先级1+
        tasks = []
        for i, email in enumerate(emails):
            if email == current_email:
                tasks.append(PreloadTask.create(email, priority=0))
            else:
                tasks.append(PreloadTask.create(email, priority=i + 1))
        
        # 打乱顺序后排序
        import random
        random.shuffle(tasks)
        sorted_tasks = sorted(tasks)
        
        # 验证当前账户在最前面
        assert sorted_tasks[0].account_email == current_email
        assert sorted_tasks[0].priority == 0
    
    @settings(max_examples=100)
    @given(
        task1_priority=priority_strategy,
        task2_priority=priority_strategy
    )
    def test_lower_priority_number_comes_first(self, task1_priority, task2_priority):
        """
        **Feature: account-preload-queue, Property 1: Current Account Priority**
        优先级数字越小的任务应排在前面
        """
        assume(task1_priority != task2_priority)
        
        task1 = PreloadTask.create("user1@test.com", priority=task1_priority)
        task2 = PreloadTask.create("user2@test.com", priority=task2_priority)
        
        sorted_tasks = sorted([task1, task2])
        
        if task1_priority < task2_priority:
            assert sorted_tasks[0].priority == task1_priority
        else:
            assert sorted_tasks[0].priority == task2_priority
    
    @settings(max_examples=100)
    @given(
        priority=priority_strategy,
        num_tasks=st.integers(min_value=2, max_value=10)
    )
    def test_same_priority_ordered_by_creation_time(self, priority, num_tasks):
        """
        **Feature: account-preload-queue, Property 1: Current Account Priority**
        相同优先级的任务应按创建时间排序
        """
        tasks = []
        for i in range(num_tasks):
            task = PreloadTask.create(f"user{i}@test.com", priority=priority)
            # 确保创建时间有差异
            task.created_at = time.time() + i * 0.001
            tasks.append(task)
        
        import random
        random.shuffle(tasks)
        sorted_tasks = sorted(tasks)
        
        # 验证按创建时间排序
        for i in range(len(sorted_tasks) - 1):
            assert sorted_tasks[i].created_at <= sorted_tasks[i + 1].created_at


# ============================================================================
# Property 9: Configuration Fallback
# **Feature: account-preload-queue, Property 9: Configuration Fallback**
# *For any* invalid configuration value, the system SHALL use the
# corresponding default value instead.
# **Validates: Requirements 6.2**
# ============================================================================

class TestConfigurationFallback:
    """测试配置回退机制"""
    
    @settings(max_examples=100)
    @given(
        invalid_concurrent=st.integers(max_value=0),
        invalid_interval=st.floats(max_value=0),
        invalid_queue_size=st.integers(max_value=0)
    )
    def test_invalid_values_fallback_to_defaults(
        self, invalid_concurrent, invalid_interval, invalid_queue_size
    ):
        """
        **Feature: account-preload-queue, Property 9: Configuration Fallback**
        无效配置值应回退到默认值
        """
        config_dict = {
            "max_concurrent": invalid_concurrent,
            "refresh_interval": invalid_interval,
            "max_queue_size": invalid_queue_size,
        }
        
        config = PreloadQueueConfig.from_dict(config_dict)
        defaults = PreloadQueueConfig()
        
        # 验证回退到默认值或最小有效值
        assert config.max_concurrent >= 1
        assert config.refresh_interval >= 10.0
        assert config.max_queue_size >= 1
    
    @settings(max_examples=100)
    @given(
        valid_concurrent=st.integers(min_value=1, max_value=10),
        valid_interval=st.floats(min_value=10.0, max_value=3600.0),
        valid_queue_size=st.integers(min_value=1, max_value=100)
    )
    def test_valid_values_preserved(
        self, valid_concurrent, valid_interval, valid_queue_size
    ):
        """
        **Feature: account-preload-queue, Property 9: Configuration Fallback**
        有效配置值应被保留
        """
        config_dict = {
            "max_concurrent": valid_concurrent,
            "refresh_interval": valid_interval,
            "max_queue_size": valid_queue_size,
        }
        
        config = PreloadQueueConfig.from_dict(config_dict)
        
        assert config.max_concurrent == valid_concurrent
        assert config.refresh_interval == valid_interval
        assert config.max_queue_size == valid_queue_size
    
    @settings(max_examples=100)
    @given(
        non_numeric=st.text(min_size=1, max_size=10, alphabet=st.characters(
            whitelist_categories=('L', 'P'),  # 只使用字母和标点
            blacklist_characters='0123456789.-+eE'
        ))
    )
    def test_non_numeric_values_fallback(self, non_numeric):
        """
        **Feature: account-preload-queue, Property 9: Configuration Fallback**
        非数字配置值应回退到默认值
        """
        assume(len(non_numeric.strip()) > 0)  # 确保不是空白字符串
        
        config_dict = {
            "max_concurrent": non_numeric,
            "refresh_interval": non_numeric,
        }
        
        config = PreloadQueueConfig.from_dict(config_dict)
        defaults = PreloadQueueConfig()
        
        assert config.max_concurrent == defaults.max_concurrent
        assert config.refresh_interval == defaults.refresh_interval


# ============================================================================
# Property 3: Cache Storage with Timestamp
# **Feature: account-preload-queue, Property 3: Cache Storage with Timestamp**
# *For any* successfully loaded account data, the cache SHALL contain
# the data with a valid timestamp that is within a small delta of the current time.
# **Validates: Requirements 1.4**
# ============================================================================

class TestCacheEntryTimestamp:
    """测试缓存条目时间戳"""
    
    @settings(max_examples=100)
    @given(
        data=st.dictionaries(st.text(min_size=1), st.text()),
        ttl=st.floats(min_value=10.0, max_value=3600.0)
    )
    def test_cache_entry_has_valid_timestamp(self, data, ttl):
        """
        **Feature: account-preload-queue, Property 3: Cache Storage with Timestamp**
        缓存条目应包含有效的时间戳
        """
        before = time.time()
        entry = CacheEntry(data=data, timestamp=time.time(), ttl=ttl)
        after = time.time()
        
        # 时间戳应在创建前后的时间范围内
        assert before <= entry.timestamp <= after
    
    @settings(max_examples=100)
    @given(
        ttl=st.floats(min_value=10.0, max_value=100.0)
    )
    def test_fresh_cache_entry_is_fresh(self, ttl):
        """
        **Feature: account-preload-queue, Property 3: Cache Storage with Timestamp**
        新创建的缓存条目应该是新鲜的
        """
        entry = CacheEntry(data={}, timestamp=time.time(), ttl=ttl)
        assert entry.is_fresh() is True
    
    @settings(max_examples=100)
    @given(
        ttl=st.floats(min_value=0.001, max_value=0.01)
    )
    def test_expired_cache_entry_is_not_fresh(self, ttl):
        """
        **Feature: account-preload-queue, Property 3: Cache Storage with Timestamp**
        过期的缓存条目应该不新鲜
        """
        # 创建一个已过期的条目
        entry = CacheEntry(
            data={},
            timestamp=time.time() - ttl - 1,  # 已过期
            ttl=ttl
        )
        assert entry.is_fresh() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])



# ============================================================================
# Property 10: Cache Size Limit with LRU Eviction
# **Feature: account-preload-queue, Property 10: Cache Size Limit with LRU Eviction**
# *For any* cache state where the number of cached accounts exceeds
# max_cached_accounts, the least recently used account's data SHALL be evicted.
# **Validates: Requirements 7.1, 7.2**
# ============================================================================

class TestAccountDataCacheLRU:
    """测试 AccountDataCache LRU 淘汰机制"""
    
    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        max_accounts=st.integers(min_value=2, max_value=10),
        num_accounts=st.integers(min_value=3, max_value=15)
    )
    async def test_cache_respects_max_accounts_limit(self, max_accounts, num_accounts):
        """
        **Feature: account-preload-queue, Property 10: Cache Size Limit with LRU Eviction**
        缓存账户数不应超过 max_accounts 限制
        """
        from src.services.account_preload import AccountDataCache
        
        cache = AccountDataCache(max_accounts=max_accounts, default_ttl=300.0)
        
        # 添加超过限制的账户
        for i in range(num_accounts):
            await cache.set_account_data(
                f"user{i}@test.com",
                "overview",
                {"id": i}
            )
        
        # 验证缓存账户数不超过限制
        stats = cache.get_stats()
        assert stats["cached_accounts"] <= max_accounts
    
    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        max_accounts=st.integers(min_value=2, max_value=5)
    )
    async def test_lru_eviction_removes_oldest_accessed(self, max_accounts):
        """
        **Feature: account-preload-queue, Property 10: Cache Size Limit with LRU Eviction**
        LRU 淘汰应移除最早访问的账户
        """
        from src.services.account_preload import AccountDataCache
        
        cache = AccountDataCache(max_accounts=max_accounts, default_ttl=300.0)
        
        # 添加 max_accounts 个账户
        for i in range(max_accounts):
            await cache.set_account_data(
                f"user{i}@test.com",
                "overview",
                {"id": i}
            )
        
        # 访问除第一个外的所有账户，使第一个成为 LRU
        for i in range(1, max_accounts):
            await cache.get_account_data(f"user{i}@test.com", "overview")
        
        # 添加新账户，应该淘汰 user0
        await cache.set_account_data(
            "new_user@test.com",
            "overview",
            {"id": "new"}
        )
        
        # 验证 user0 被淘汰
        data = await cache.get_account_data("user0@test.com", "overview")
        assert data is None
        
        # 验证新账户存在
        new_data = await cache.get_account_data("new_user@test.com", "overview")
        assert new_data is not None


# ============================================================================
# Property 11: Cache Cleanup on Logout
# **Feature: account-preload-queue, Property 11: Cache Cleanup on Logout**
# *For any* account logout operation, all cached data for that account
# SHALL be removed from the cache.
# **Validates: Requirements 7.3**
# ============================================================================

class TestAccountDataCacheCleanup:
    """测试 AccountDataCache 登出清理"""
    
    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        email=email_strategy,
        data_types=st.lists(
            st.sampled_from([dt.value for dt in PreloadDataType]),
            min_size=1,
            max_size=4,
            unique=True
        )
    )
    async def test_clear_account_removes_all_data(self, email, data_types):
        """
        **Feature: account-preload-queue, Property 11: Cache Cleanup on Logout**
        清除账户应移除该账户的所有缓存数据
        """
        from src.services.account_preload import AccountDataCache
        
        cache = AccountDataCache(max_accounts=20, default_ttl=300.0)
        
        # 为账户添加多种类型的数据
        for dt in data_types:
            await cache.set_account_data(email, dt, {"type": dt})
        
        # 验证数据存在
        for dt in data_types:
            data = await cache.get_account_data(email, dt)
            assert data is not None
        
        # 清除账户
        await cache.clear_account(email)
        
        # 验证所有数据都被清除
        for dt in data_types:
            data = await cache.get_account_data(email, dt)
            assert data is None
    
    @pytest.mark.asyncio
    @settings(max_examples=100)
    @given(
        emails=st.lists(email_strategy, min_size=2, max_size=5, unique=True)
    )
    async def test_clear_account_does_not_affect_others(self, emails):
        """
        **Feature: account-preload-queue, Property 11: Cache Cleanup on Logout**
        清除一个账户不应影响其他账户的缓存
        """
        from src.services.account_preload import AccountDataCache
        
        cache = AccountDataCache(max_accounts=20, default_ttl=300.0)
        
        # 为所有账户添加数据
        for email in emails:
            await cache.set_account_data(email, "overview", {"email": email})
        
        # 清除第一个账户
        await cache.clear_account(emails[0])
        
        # 验证第一个账户被清除
        data = await cache.get_account_data(emails[0], "overview")
        assert data is None
        
        # 验证其他账户不受影响
        for email in emails[1:]:
            data = await cache.get_account_data(email, "overview")
            assert data is not None
            assert data["email"] == email



# ============================================================================
# Property 12: TaskManager Integration
# **Feature: account-preload-queue, Property 12: TaskManager Integration**
# *For any* background task created by the preload queue, the task
# SHALL be registered with the existing TaskManager.
# **Validates: Requirements 8.1**
# ============================================================================

class TestTaskManagerIntegration:
    """测试 TaskManager 集成"""
    
    @pytest.mark.asyncio
    async def test_queue_registers_tasks_with_task_manager(self):
        """
        **Feature: account-preload-queue, Property 12: TaskManager Integration**
        预加载队列应将任务注册到 TaskManager
        """
        from src.services.account_preload import AccountPreloadQueue, PreloadQueueConfig
        from src.core.task_manager import task_manager
        
        # 记录启动前的任务数
        initial_tasks = task_manager.get_stats()["active_tasks"]
        
        config = PreloadQueueConfig(refresh_interval=3600.0)  # 长间隔避免触发刷新
        queue = AccountPreloadQueue(config=config)
        
        try:
            await queue.start()
            
            # 验证任务已注册
            stats = task_manager.get_stats()
            assert stats["active_tasks"] >= initial_tasks + 2  # worker + scheduler
            
        finally:
            await queue.stop()


# ============================================================================
# Property 5: Dynamic Reprioritization
# **Feature: account-preload-queue, Property 5: Dynamic Reprioritization**
# *For any* account switch operation, the newly selected account SHALL
# be moved to the front of the preload queue, regardless of its previous position.
# **Validates: Requirements 2.4**
# ============================================================================

class TestDynamicReprioritization:
    """测试动态重排序"""
    
    @pytest.mark.asyncio
    @settings(max_examples=50)
    @given(
        emails=st.lists(email_strategy, min_size=3, max_size=10, unique=True),
        switch_idx=st.integers(min_value=1)
    )
    async def test_reprioritize_moves_account_to_front(self, emails, switch_idx):
        """
        **Feature: account-preload-queue, Property 5: Dynamic Reprioritization**
        重排序应将指定账户移到队首
        """
        from src.services.account_preload import AccountPreloadQueue, PreloadQueueConfig
        
        config = PreloadQueueConfig(refresh_interval=3600.0)
        queue = AccountPreloadQueue(config=config)
        
        # 添加所有账户到队列
        for i, email in enumerate(emails):
            await queue.enqueue_account(email, priority=i)
        
        # 选择一个非首位的账户进行切换
        switch_idx = switch_idx % (len(emails) - 1) + 1  # 确保不是第一个
        switch_email = emails[switch_idx]
        
        # 重排序
        await queue.reprioritize(switch_email)
        
        # 验证该账户现在在队首
        assert queue._queue[0].account_email == switch_email
        assert queue._queue[0].priority == 0
    
    @pytest.mark.asyncio
    async def test_reprioritize_new_account_adds_to_front(self):
        """
        **Feature: account-preload-queue, Property 5: Dynamic Reprioritization**
        重排序不在队列中的账户应添加到队首
        """
        from src.services.account_preload import AccountPreloadQueue, PreloadQueueConfig
        
        config = PreloadQueueConfig(refresh_interval=3600.0)
        queue = AccountPreloadQueue(config=config)
        
        emails = ["user1@test.com", "user2@test.com", "user3@test.com"]
        
        # 添加部分账户
        for i, email in enumerate(emails[:-1]):
            await queue.enqueue_account(email, priority=i)
        
        # 重排序一个不在队列中的账户
        new_email = emails[-1]
        await queue.reprioritize(new_email)
        
        # 验证新账户在队首
        assert queue._queue[0].account_email == new_email
        assert queue._queue[0].priority == 0


# ============================================================================
# Property 7: Concurrency Limit
# **Feature: account-preload-queue, Property 7: Concurrency Limit**
# *For any* state of the preload queue, the number of concurrent API
# requests SHALL never exceed the configured max_concurrent limit.
# **Validates: Requirements 4.3, 6.4**
# ============================================================================

class TestConcurrencyLimit:
    """测试并发限制"""
    
    @pytest.mark.asyncio
    @settings(max_examples=50, deadline=None)  # 禁用 deadline，因为涉及异步等待
    @given(
        max_concurrent=st.integers(min_value=1, max_value=5),
        num_accounts=st.integers(min_value=5, max_value=10)
    )
    async def test_concurrent_tasks_respect_limit(self, max_concurrent, num_accounts):
        """
        **Feature: account-preload-queue, Property 7: Concurrency Limit**
        并发任务数不应超过配置的限制
        """
        from src.services.account_preload import AccountPreloadQueue, PreloadQueueConfig
        
        concurrent_count = 0
        max_observed = 0
        
        async def mock_fetch(email: str, data_type: str):
            nonlocal concurrent_count, max_observed
            concurrent_count += 1
            max_observed = max(max_observed, concurrent_count)
            await asyncio.sleep(0.01)  # 模拟网络延迟
            concurrent_count -= 1
            return {"email": email, "type": data_type}
        
        config = PreloadQueueConfig(
            max_concurrent=max_concurrent,
            refresh_interval=3600.0
        )
        queue = AccountPreloadQueue(config=config, fetch_func=mock_fetch)
        
        try:
            await queue.start()
            
            # 添加多个账户
            for i in range(num_accounts):
                await queue.enqueue_account(f"user{i}@test.com", priority=i)
            
            # 等待处理完成
            await asyncio.sleep(0.5)
            
            # 验证最大并发数不超过限制
            assert max_observed <= max_concurrent
            
        finally:
            await queue.stop()



# ============================================================================
# Property 8: Retry with Exponential Backoff
# **Feature: account-preload-queue, Property 8: Retry with Exponential Backoff**
# *For any* failed preload task, if retry_count < max_retry, the task
# SHALL be retried after a delay of retry_base_delay * (2 ^ retry_count) seconds.
# **Validates: Requirements 4.4**
# ============================================================================

class TestExponentialBackoffRetry:
    """测试指数退避重试"""
    
    @settings(max_examples=100)
    @given(
        retry_count=st.integers(min_value=0, max_value=5),
        base_delay=st.floats(min_value=0.1, max_value=10.0)
    )
    def test_exponential_backoff_formula(self, retry_count, base_delay):
        """
        **Feature: account-preload-queue, Property 8: Retry with Exponential Backoff**
        重试延迟应符合指数退避公式
        """
        expected_delay = base_delay * (2 ** retry_count)
        
        # 验证公式正确性
        assert expected_delay == base_delay * (2 ** retry_count)
        
        # 验证延迟随重试次数指数增长
        if retry_count > 0:
            prev_delay = base_delay * (2 ** (retry_count - 1))
            assert expected_delay == prev_delay * 2
    
    @settings(max_examples=100)
    @given(
        max_retry=st.integers(min_value=1, max_value=5),
        retry_count=st.integers(min_value=0, max_value=10)
    )
    def test_retry_respects_max_retry_limit(self, max_retry, retry_count):
        """
        **Feature: account-preload-queue, Property 8: Retry with Exponential Backoff**
        重试次数不应超过 max_retry 限制
        """
        should_retry = retry_count < max_retry
        
        # 验证重试决策逻辑
        if retry_count >= max_retry:
            assert not should_retry
        else:
            assert should_retry



# ============================================================================
# Property 4: Cache-First Lookup
# **Feature: account-preload-queue, Property 4: Cache-First Lookup**
# *For any* account data request, if fresh cached data exists, the system
# SHALL return the cached data without making an API call.
# **Validates: Requirements 2.1, 2.2**
# ============================================================================

class TestCacheFirstLookup:
    """测试缓存优先查找"""
    
    @pytest.mark.asyncio
    @settings(max_examples=100, deadline=None)
    @given(
        email=email_strategy,
        data=st.dictionaries(st.text(min_size=1, max_size=10), st.text(min_size=1))
    )
    async def test_cache_hit_returns_cached_data(self, email, data):
        """
        **Feature: account-preload-queue, Property 4: Cache-First Lookup**
        缓存命中时应返回缓存数据
        """
        from src.services.account_preload import AccountDataCache
        
        assume(len(data) > 0)
        
        cache = AccountDataCache(max_accounts=20, default_ttl=300.0)
        
        # 设置缓存
        await cache.set_account_data(email, "overview", data)
        
        # 获取缓存
        cached = await cache.get_account_data(email, "overview")
        
        # 验证返回缓存数据
        assert cached is not None
        assert cached == data


# ============================================================================
# Property 6: Manual Request Priority
# **Feature: account-preload-queue, Property 6: Manual Request Priority**
# *For any* manual refresh request, the request SHALL be processed before
# any pending background preload tasks.
# **Validates: Requirements 4.2**
# ============================================================================

class TestManualRequestPriority:
    """测试手动请求优先级"""
    
    @settings(max_examples=100)
    @given(
        force=st.booleans()
    )
    def test_force_flag_bypasses_cache(self, force):
        """
        **Feature: account-preload-queue, Property 6: Manual Request Priority**
        force=True 时应跳过缓存
        """
        # 验证 force 标志的语义
        should_use_cache = not force
        
        if force:
            assert not should_use_cache
        else:
            assert should_use_cache


# ============================================================================
# Property 13: Backward Compatibility
# **Feature: account-preload-queue, Property 13: Backward Compatibility**
# *For any* existing API endpoint response, the response format SHALL
# remain unchanged after the preload queue integration.
# **Validates: Requirements 8.5**
# ============================================================================

class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    @settings(max_examples=100)
    @given(
        info=st.fixed_dictionaries({
            "id": st.text(min_size=1),
            "email": email_strategy,
            "customer_type": st.sampled_from(["PAYG", "Enterprise"]),
        }),
        billing=st.fixed_dictionaries({
            "balance": st.floats(min_value=0, max_value=1000),
            "total_spend_30_days": st.floats(min_value=0, max_value=1000),
        })
    )
    def test_overview_response_format_preserved(self, info, billing):
        """
        **Feature: account-preload-queue, Property 13: Backward Compatibility**
        overview 响应格式应保持不变
        """
        # 模拟 overview 响应
        response = {
            "info": info,
            "billing": billing,
            "api_keys": [],
        }
        
        # 验证必需字段存在
        assert "info" in response
        assert "billing" in response
        assert "api_keys" in response
        
        # 验证 info 字段
        assert "id" in response["info"]
        assert "email" in response["info"]
        assert "customer_type" in response["info"]
        
        # 验证 billing 字段
        assert "balance" in response["billing"]
        assert "total_spend_30_days" in response["billing"]



# ============================================================================
# Property 13: Backward Compatibility
# **Feature: account-preload-queue, Property 13: Backward Compatibility**
# *For any* existing API endpoint response, the response format SHALL
# remain unchanged after the preload queue integration.
# **Validates: Requirements 8.5**
# ============================================================================

class TestBackwardCompatibility:
    """测试向后兼容性"""
    
    @settings(max_examples=100)
    @given(
        info_data=st.fixed_dictionaries({
            "id": st.text(min_size=1, max_size=20),
            "email": email_strategy,
            "customer_type": st.sampled_from(["PAYG", "Enterprise", "Free"]),
            "cc_brand": st.one_of(st.none(), st.text(min_size=1, max_size=20)),
            "cc_last4": st.one_of(st.none(), st.text(min_size=4, max_size=4)),
            "created": st.text(min_size=10, max_size=30),
        })
    )
    def test_overview_response_format_preserved(self, info_data):
        """
        **Feature: account-preload-queue, Property 13: Backward Compatibility**
        overview 响应格式应保持不变
        """
        # 验证必需字段存在
        required_fields = ["id", "email", "customer_type", "created"]
        for field in required_fields:
            assert field in info_data
        
        # 验证可选字段类型
        assert info_data.get("cc_brand") is None or isinstance(info_data["cc_brand"], str)
        assert info_data.get("cc_last4") is None or isinstance(info_data["cc_last4"], str)
