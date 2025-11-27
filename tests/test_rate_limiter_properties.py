# Feature: api-key-management-enhancement, Property 6: 速率限制状态管理
# Feature: api-key-management-enhancement, Property 7: 速率限制自动重置
"""
速率限制管理器属性测试
测试速率限制的跟踪、状态管理和自动重置功能
"""
import pytest
import asyncio
import time
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rate_limiter import RateLimiter, get_rate_limiter
from src.models_key import RateLimitInfo, KeyStatus


class TestRateLimiter:
    """速率限制管理器测试"""
    
    @pytest.fixture
    def rate_limiter(self):
        """创建速率限制管理器实例"""
        limiter = RateLimiter()
        limiter._initialized = True  # 跳过初始化
        limiter._rate_limits = {}
        return limiter
    
    # Feature: api-key-management-enhancement, Property 6: 速率限制状态管理
    # **Validates: Requirements 2.3**
    @given(
        key_index=st.integers(min_value=0, max_value=10),
        limit=st.integers(min_value=1, max_value=1000),
        remaining=st.integers(min_value=0, max_value=1000),
        reset_time_offset=st.integers(min_value=1, max_value=3600)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rate_limit_status_management(self, rate_limiter, key_index, limit, remaining, reset_time_offset):
        """测试速率限制状态管理"""
        assume(remaining <= limit)
        
        current_time = int(time.time())
        reset_time = current_time + reset_time_offset
        
        # 同步运行异步函数
        async def run_test():
            # 更新速率限制信息
            await rate_limiter.update_rate_limit(key_index, limit, remaining, reset_time)
            
            # 验证信息被正确存储
            info = await rate_limiter.get_rate_limit_info(key_index)
            assert info is not None, f"Rate limit info should exist for key {key_index}"
            assert info.key_index == key_index, f"Key index mismatch"
            assert info.limit == limit, f"Limit mismatch"
            assert info.remaining == remaining, f"Remaining mismatch"
            assert info.used == limit - remaining, f"Used mismatch"
            
            # 验证状态正确设置
            if remaining <= 0:
                assert info.status == KeyStatus.EXHAUSTED
                exhausted = await rate_limiter.is_key_exhausted(key_index)
                assert exhausted, f"Key {key_index} should be exhausted"
            else:
                assert info.status == KeyStatus.ACTIVE
                exhausted = await rate_limiter.is_key_exhausted(key_index)
                assert not exhausted, f"Key {key_index} should not be exhausted"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 7: 速率限制自动重置
    # **Validates: Requirements 2.5**
    def test_rate_limit_auto_reset(self, rate_limiter):
        """测试速率限制自动重置"""
        async def run_test():
            key_index = 0
            limit = 100
            
            current_time = int(time.time())
            # 设置重置时间为过去（已经过期）
            reset_time = current_time - 1
            
            # 设置密钥为已用尽状态
            await rate_limiter.update_rate_limit(key_index, limit, 0, reset_time)
            
            # 由于重置时间已过，检查时应该自动重置
            reset_occurred = await rate_limiter.reset_key_if_time_reached(key_index)
            assert reset_occurred, "Key should have been reset"
            
            # 验证重置后的状态
            info = await rate_limiter.get_rate_limit_info(key_index)
            assert info.status == KeyStatus.ACTIVE, "Key should be ACTIVE after reset"
            assert info.remaining == limit, f"Remaining should be {limit} after reset"
            assert info.used == 0, "Used should be 0 after reset"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        key_indices=st.lists(st.integers(min_value=0, max_value=10), min_size=1, max_size=5, unique=True),
        limits=st.lists(st.integers(min_value=10, max_value=100), min_size=5, max_size=5),
        remainings=st.lists(st.integers(min_value=0, max_value=100), min_size=5, max_size=5)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_get_next_available_key(self, rate_limiter, key_indices, limits, remainings):
        """测试获取下一个可用密钥"""
        async def run_test():
            current_time = int(time.time())
            
            # 设置多个密钥的状态
            for i, idx in enumerate(key_indices):
                limit = limits[i % len(limits)]
                remaining = remainings[i % len(remainings)]
                # 确保 remaining <= limit
                remaining = min(remaining, limit)
                reset_time = current_time + 3600  # 1小时后重置
                await rate_limiter.update_rate_limit(idx, limit, remaining, reset_time)
            
            # 获取可用密钥
            available = await rate_limiter.get_next_available_key(key_indices)
            
            # 验证返回的密钥
            if available is not None:
                # 如果有可用密钥，应该是未用尽的
                info = await rate_limiter.get_rate_limit_info(available)
                if info:
                    # 检查是否有任何未用尽的密钥
                    has_available = False
                    for idx in key_indices:
                        idx_info = await rate_limiter.get_rate_limit_info(idx)
                        if idx_info and idx_info.remaining > 0:
                            has_available = True
                            break
                    
                    if has_available:
                        # 如果有可用密钥，返回的应该是可用的
                        assert info.remaining > 0 or info.status == KeyStatus.ACTIVE
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_get_earliest_reset_time(self, rate_limiter):
        """测试获取最早重置时间"""
        async def run_test():
            current_time = int(time.time())
            
            # 设置不同的重置时间
            await rate_limiter.update_rate_limit(0, 100, 0, current_time + 3600)  # 1小时后
            await rate_limiter.update_rate_limit(1, 100, 0, current_time + 1800)  # 30分钟后
            await rate_limiter.update_rate_limit(2, 100, 0, current_time + 7200)  # 2小时后
            
            earliest = await rate_limiter.get_earliest_reset_time([0, 1, 2])
            assert earliest == current_time + 1800, f"Earliest reset should be {current_time + 1800}"
            
            # 测试空列表
            earliest_empty = await rate_limiter.get_earliest_reset_time([])
            assert earliest_empty is None, "Should return None for empty list"
            
            # 测试不存在的密钥
            earliest_missing = await rate_limiter.get_earliest_reset_time([99])
            assert earliest_missing is None, "Should return None for non-existent keys"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_get_all_rate_limits(self, rate_limiter):
        """测试获取所有速率限制信息"""
        async def run_test():
            current_time = int(time.time())
            
            # 设置多个密钥的速率限制
            await rate_limiter.update_rate_limit(0, 100, 50, current_time + 3600)
            await rate_limiter.update_rate_limit(1, 200, 0, current_time + 1800)
            await rate_limiter.update_rate_limit(2, 150, 75, current_time + 7200)
            
            all_limits = await rate_limiter.get_all_rate_limits()
            
            assert len(all_limits) == 3, f"Should have 3 rate limits, got {len(all_limits)}"
            
            # 验证每个密钥的信息
            assert 0 in all_limits
            assert all_limits[0].limit == 100
            assert all_limits[0].remaining == 50
            
            assert 1 in all_limits
            assert all_limits[1].limit == 200
            assert all_limits[1].remaining == 0
            assert all_limits[1].status == KeyStatus.EXHAUSTED
            
            assert 2 in all_limits
            assert all_limits[2].limit == 150
            assert all_limits[2].remaining == 75
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestRateLimiterIntegration:
    """速率限制管理器集成测试"""
    
    def test_global_rate_limiter(self):
        """测试全局速率限制管理器实例"""
        async def run_test():
            with patch('src.rate_limiter.get_storage_adapter') as mock_adapter:
                mock_storage = AsyncMock()
                mock_adapter.return_value = mock_storage
                mock_storage.get_config.return_value = {}
                
                # 重置全局实例
                import src.rate_limiter as rl_module
                rl_module._rate_limiter = None
                
                limiter1 = await get_rate_limiter()
                limiter2 = await get_rate_limiter()
                
                # 应该返回同一个实例
                assert limiter1 is limiter2
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=5),  # key_index
                st.integers(min_value=10, max_value=100),  # limit
                st.integers(min_value=0, max_value=100),  # remaining
            ),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=20)
    def test_multiple_rate_limit_updates(self, operations):
        """测试多次速率限制更新"""
        async def run_test():
            limiter = RateLimiter()
            limiter._initialized = True
            limiter._rate_limits = {}
            
            current_time = int(time.time())
            
            for key_index, limit, remaining in operations:
                # 确保 remaining <= limit
                remaining = min(remaining, limit)
                reset_time = current_time + 3600
                
                await limiter.update_rate_limit(key_index, limit, remaining, reset_time)
                
                # 验证更新后的状态
                info = await limiter.get_rate_limit_info(key_index)
                assert info is not None
                assert info.limit == limit
                assert info.remaining == remaining
                
                # 验证状态一致性
                if remaining <= 0:
                    assert info.status == KeyStatus.EXHAUSTED
                else:
                    assert info.status == KeyStatus.ACTIVE
        
        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
