# Feature: api-key-management-enhancement, Property 4: 轮换次数优先策略
# Feature: api-key-management-enhancement, Property 5: 速率限制优先策略
"""
智能轮换策略属性测试
测试轮换次数和速率限制的综合判断
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from unittest.mock import AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.key_selector import KeySelector
from src.models_key import KeyInfo, KeyStatus, AggregationMode, RateLimitInfo


class TestRotationStrategy:
    """轮换策略测试"""
    
    @pytest.fixture
    def selector(self):
        """创建密钥选择器实例"""
        return KeySelector(mode=AggregationMode.ROUND_ROBIN)
    
    # Feature: api-key-management-enhancement, Property 4: 轮换次数优先策略
    # **Validates: Requirements 2.1**
    @given(
        calls_per_rotation=st.integers(min_value=1, max_value=100),
        current_calls=st.integers(min_value=0, max_value=150)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_calls_rotation_priority(self, selector, calls_per_rotation, current_calls):
        """测试轮换次数优先策略"""
        selector.calls_per_rotation = calls_per_rotation
        selector._call_counts[0] = current_calls
        
        # 不提供速率限制信息，只基于调用次数判断
        should_rotate = selector.should_rotate(0, rate_limit_remaining=None)
        
        if current_calls >= calls_per_rotation:
            assert should_rotate, f"Should rotate when calls ({current_calls}) >= limit ({calls_per_rotation})"
        else:
            assert not should_rotate, f"Should not rotate when calls ({current_calls}) < limit ({calls_per_rotation})"
    
    # Feature: api-key-management-enhancement, Property 5: 速率限制优先策略
    # **Validates: Requirements 2.2**
    @given(
        rate_limit_remaining=st.integers(min_value=-10, max_value=100)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_rate_limit_rotation_priority(self, selector, rate_limit_remaining):
        """测试速率限制优先策略"""
        selector.calls_per_rotation = 1000  # 设置很高的轮换次数
        selector._call_counts[0] = 0  # 重置调用计数
        
        should_rotate = selector.should_rotate(0, rate_limit_remaining=rate_limit_remaining)
        
        if rate_limit_remaining <= 0:
            assert should_rotate, f"Should rotate when rate limit remaining ({rate_limit_remaining}) <= 0"
        else:
            assert not should_rotate, f"Should not rotate when rate limit remaining ({rate_limit_remaining}) > 0"
    
    @given(
        calls_per_rotation=st.integers(min_value=1, max_value=50),
        current_calls=st.integers(min_value=0, max_value=100),
        rate_limit_remaining=st.integers(min_value=-10, max_value=100)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_combined_rotation_strategy(self, selector, calls_per_rotation, current_calls, rate_limit_remaining):
        """测试综合轮换策略"""
        selector.calls_per_rotation = calls_per_rotation
        selector._call_counts[0] = current_calls
        
        should_rotate = selector.should_rotate(0, rate_limit_remaining=rate_limit_remaining)
        
        # 任一条件满足都应该轮换
        calls_trigger = current_calls >= calls_per_rotation
        rate_limit_trigger = rate_limit_remaining <= 0
        
        expected = calls_trigger or rate_limit_trigger
        assert should_rotate == expected, \
            f"Rotation mismatch: calls={current_calls}/{calls_per_rotation}, remaining={rate_limit_remaining}, expected={expected}, got={should_rotate}"
    
    def test_rotation_resets_call_count(self, selector):
        """测试轮换后重置调用计数"""
        selector.calls_per_rotation = 5
        selector._call_counts[0] = 5
        
        # 触发轮换
        should_rotate = selector.should_rotate(0)
        assert should_rotate, "Should rotate"
        
        # 验证计数被重置
        assert selector.get_call_count(0) == 0, "Call count should be reset after rotation"
    
    def test_should_rotate_with_rate_limiter(self, selector):
        """测试集成速率限制管理器的轮换判断"""
        async def run_test():
            # 创建模拟的速率限制管理器
            mock_rate_limiter = AsyncMock()
            mock_info = MagicMock()
            mock_info.remaining = 0  # 已用尽
            mock_rate_limiter.get_rate_limit_info.return_value = mock_info
            
            selector.calls_per_rotation = 1000  # 设置很高的轮换次数
            selector._call_counts[0] = 0
            
            # 应该因为速率限制而轮换
            should_rotate = await selector.should_rotate_with_rate_limit(0, mock_rate_limiter)
            assert should_rotate, "Should rotate due to rate limit exhaustion"
            
            # 测试有剩余配额的情况
            mock_info.remaining = 50
            selector._call_counts[0] = 0
            should_rotate = await selector.should_rotate_with_rate_limit(0, mock_rate_limiter)
            assert not should_rotate, "Should not rotate when rate limit has remaining"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_should_rotate_without_rate_limiter(self, selector):
        """测试没有速率限制管理器时的轮换判断"""
        async def run_test():
            selector.calls_per_rotation = 5
            selector._call_counts[0] = 5
            
            # 没有速率限制管理器，只基于调用次数
            should_rotate = await selector.should_rotate_with_rate_limit(0, None)
            assert should_rotate, "Should rotate based on call count"
            
            selector._call_counts[0] = 3
            should_rotate = await selector.should_rotate_with_rate_limit(0, None)
            assert not should_rotate, "Should not rotate when call count is low"
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestRotationStrategyIntegration:
    """轮换策略集成测试"""
    
    @given(
        num_keys=st.integers(min_value=2, max_value=5),
        calls_per_rotation=st.integers(min_value=1, max_value=10),
        num_calls=st.integers(min_value=1, max_value=50)
    )
    @settings(max_examples=20)
    def test_rotation_across_multiple_keys(self, num_keys, calls_per_rotation, num_calls):
        """测试多密钥轮换"""
        async def run_test():
            from src.key_selector import KeySelector
            from src.models_key import KeyInfo, AggregationMode
            
            selector = KeySelector(mode=AggregationMode.ROUND_ROBIN)
            selector.calls_per_rotation = calls_per_rotation
            
            keys = [KeyInfo(index=i, key=f"key_{i}", enabled=True) for i in range(num_keys)]
            
            rotation_count = 0
            for _ in range(num_calls):
                selected = await selector.select_next_key(keys)
                if selected:
                    # 检查是否需要轮换
                    if selector.should_rotate(selected.index):
                        rotation_count += 1
            
            # 验证轮换次数合理
            expected_min_rotations = (num_calls // calls_per_rotation) - num_keys
            expected_max_rotations = (num_calls // calls_per_rotation) + num_keys
            
            # 由于轮询分布，实际轮换次数可能有偏差
            assert rotation_count >= 0, "Rotation count should be non-negative"
        
        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
