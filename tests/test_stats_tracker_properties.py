# Feature: api-key-management-enhancement, Property 8: 活跃密钥计数准确性
# Feature: api-key-management-enhancement, Property 9: 统计结果分组显示
# Feature: api-key-management-enhancement, Property 19: 密钥统计信息完整性
# Feature: api-key-management-enhancement, Property 20: 统计信息实时更新
"""
统计跟踪器属性测试
测试统计数据的准确性、分组显示和实时更新
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.stats_tracker import StatsTracker, get_stats_tracker
from src.models_key import KeyInfo, KeyStats, RateLimitInfo, KeyStatus


def create_key_info(index: int, enabled: bool = True) -> KeyInfo:
    """创建测试用的 KeyInfo"""
    return KeyInfo(
        index=index,
        key=f"test_key_{index}",
        enabled=enabled,
        status=KeyStatus.ACTIVE
    )


class TestStatsTracker:
    """统计跟踪器测试"""
    
    @pytest.fixture
    def tracker(self):
        """创建统计跟踪器实例"""
        t = StatsTracker()
        t._initialized = True
        t._stats = {}
        return t
    
    # Feature: api-key-management-enhancement, Property 8: 活跃密钥计数准确性
    # **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
    @given(
        num_keys=st.integers(min_value=1, max_value=10),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=0, max_size=5, unique=True)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_active_key_count_accuracy(self, tracker, num_keys, disabled_indices):
        """测试活跃密钥计数准确性"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < num_keys]
        
        # 创建密钥列表
        keys = []
        for i in range(num_keys):
            enabled = i not in valid_disabled
            keys.append(create_key_info(i, enabled=enabled))
        
        async def run_test():
            # 获取所有统计
            stats = await tracker.get_all_stats(keys)
            
            # 验证活跃密钥数量
            expected_active = num_keys - len(valid_disabled)
            assert stats["active_keys"] == expected_active, \
                f"Active keys mismatch: expected {expected_active}, got {stats['active_keys']}"
            
            # 验证禁用密钥数量
            assert stats["disabled_keys"] == len(valid_disabled), \
                f"Disabled keys mismatch: expected {len(valid_disabled)}, got {stats['disabled_keys']}"
            
            # 验证总数
            assert stats["total_keys"] == num_keys, \
                f"Total keys mismatch: expected {num_keys}, got {stats['total_keys']}"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 9: 统计结果分组显示
    # **Validates: Requirements 3.6, 3.7**
    @given(
        num_keys=st.integers(min_value=2, max_value=8),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=7), min_size=1, max_size=4, unique=True)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_stats_grouping(self, tracker, num_keys, disabled_indices):
        """测试统计结果分组显示"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < num_keys]
        assume(len(valid_disabled) > 0 and len(valid_disabled) < num_keys)
        
        # 创建密钥列表
        keys = []
        for i in range(num_keys):
            enabled = i not in valid_disabled
            keys.append(create_key_info(i, enabled=enabled))
        
        async def run_test():
            # 获取分组统计
            stats = await tracker.get_all_stats(keys, group_by_status=True)
            
            # 验证分组存在
            assert "enabled" in stats, "Should have 'enabled' group"
            assert "disabled" in stats, "Should have 'disabled' group"
            
            # 验证分组数量
            assert len(stats["enabled"]) == num_keys - len(valid_disabled), \
                f"Enabled group size mismatch"
            assert len(stats["disabled"]) == len(valid_disabled), \
                f"Disabled group size mismatch"
            
            # 验证分组内容正确
            enabled_indices = [s["key_index"] for s in stats["enabled"]]
            disabled_indices_result = [s["key_index"] for s in stats["disabled"]]
            
            for i in range(num_keys):
                if i in valid_disabled:
                    assert i in disabled_indices_result, f"Key {i} should be in disabled group"
                else:
                    assert i in enabled_indices, f"Key {i} should be in enabled group"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 19: 密钥统计信息完整性
    # **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**
    @given(
        key_index=st.integers(min_value=0, max_value=10),
        success_count=st.integers(min_value=0, max_value=100),
        failure_count=st.integers(min_value=0, max_value=50)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_key_stats_completeness(self, tracker, key_index, success_count, failure_count):
        """测试密钥统计信息完整性"""
        async def run_test():
            # 重置 tracker 状态
            tracker._stats = {}
            
            # 记录调用
            for _ in range(success_count):
                await tracker.record_call(key_index, True, "test-model", f"key_{key_index}***")
            for _ in range(failure_count):
                await tracker.record_call(key_index, False, "test-model", f"key_{key_index}***")
            
            # 获取统计
            key_info = create_key_info(key_index)
            stats = await tracker.get_key_stats(key_index, key_info)
            
            # 验证统计完整性
            assert stats.key_index == key_index, "Key index mismatch"
            assert stats.success_count == success_count, \
                f"Success count mismatch: expected {success_count}, got {stats.success_count}"
            assert stats.failure_count == failure_count, \
                f"Failure count mismatch: expected {failure_count}, got {stats.failure_count}"
            assert stats.total_count == success_count + failure_count, \
                f"Total calls mismatch"
            
            # 验证模型计数
            if success_count + failure_count > 0:
                assert "test-model" in stats.model_counts, "Model should be in model_counts"
                assert stats.model_counts["test-model"] == success_count + failure_count, \
                    "Model count mismatch"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 20: 统计信息实时更新
    # **Validates: Requirements 6.6**
    @given(
        initial_calls=st.integers(min_value=0, max_value=10),
        additional_calls=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_stats_realtime_update(self, tracker, initial_calls, additional_calls):
        """测试统计信息实时更新"""
        async def run_test():
            # 重置 tracker 状态
            tracker._stats = {}
            
            key_index = 0
            
            # 记录初始调用
            for _ in range(initial_calls):
                await tracker.record_call(key_index, True, "model-a")
            
            # 获取初始统计
            key_info = create_key_info(key_index)
            stats_before = await tracker.get_key_stats(key_index, key_info)
            assert stats_before.success_count == initial_calls, "Initial count mismatch"
            
            # 记录额外调用
            for _ in range(additional_calls):
                await tracker.record_call(key_index, True, "model-b")
            
            # 获取更新后的统计
            stats_after = await tracker.get_key_stats(key_index, key_info)
            
            # 验证实时更新
            assert stats_after.success_count == initial_calls + additional_calls, \
                f"Updated count mismatch: expected {initial_calls + additional_calls}, got {stats_after.success_count}"
            
            # 验证模型计数更新
            assert "model-a" in stats_after.model_counts or initial_calls == 0
            assert "model-b" in stats_after.model_counts
            if initial_calls > 0:
                assert stats_after.model_counts.get("model-a", 0) == initial_calls
            assert stats_after.model_counts.get("model-b", 0) == additional_calls
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_reset_stats(self, tracker):
        """测试重置统计"""
        async def run_test():
            # 记录一些调用
            await tracker.record_call(0, True, "model")
            await tracker.record_call(0, False, "model")
            await tracker.record_call(1, True, "model")
            
            # 验证有数据
            key_info_0 = create_key_info(0)
            stats_0 = await tracker.get_key_stats(0, key_info_0)
            assert stats_0.success_count == 1
            assert stats_0.failure_count == 1
            
            # 重置单个密钥
            await tracker.reset_stats(0)
            stats_0_after = await tracker.get_key_stats(0, key_info_0)
            assert stats_0_after.success_count == 0
            assert stats_0_after.failure_count == 0
            
            # 验证其他密钥不受影响
            key_info_1 = create_key_info(1)
            stats_1 = await tracker.get_key_stats(1, key_info_1)
            assert stats_1.success_count == 1
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    def test_get_active_keys_stats(self, tracker):
        """测试获取活跃密钥统计"""
        async def run_test():
            # 创建混合状态的密钥
            keys = [
                create_key_info(0, enabled=True),
                create_key_info(1, enabled=False),
                create_key_info(2, enabled=True),
            ]
            
            # 记录调用
            await tracker.record_call(0, True, "model")
            await tracker.record_call(1, True, "model")  # 禁用密钥也记录
            await tracker.record_call(2, True, "model")
            await tracker.record_call(2, True, "model")
            
            # 获取活跃密钥统计
            stats = await tracker.get_active_keys_stats(keys)
            
            # 验证只包含活跃密钥
            assert stats["active_keys"] == 2, "Should have 2 active keys"
            assert len(stats["keys"]) == 2, "Should return 2 key stats"
            
            # 验证统计正确
            key_indices = [s["key_index"] for s in stats["keys"]]
            assert 0 in key_indices
            assert 2 in key_indices
            assert 1 not in key_indices  # 禁用密钥不应该在结果中
        
        asyncio.get_event_loop().run_until_complete(run_test())


class TestStatsTrackerIntegration:
    """统计跟踪器集成测试"""
    
    def test_global_stats_tracker(self):
        """测试全局统计跟踪器实例"""
        async def run_test():
            with patch('src.stats_tracker.get_storage_adapter') as mock_adapter:
                mock_storage = AsyncMock()
                mock_adapter.return_value = mock_storage
                mock_storage.get_config.return_value = {}
                
                # 重置全局实例
                import src.stats_tracker as st_module
                st_module._stats_tracker = None
                
                tracker1 = await get_stats_tracker()
                tracker2 = await get_stats_tracker()
                
                # 应该返回同一个实例
                assert tracker1 is tracker2
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        operations=st.lists(
            st.tuples(
                st.integers(min_value=0, max_value=5),  # key_index
                st.booleans(),  # success
                st.sampled_from(["model-a", "model-b", "model-c"])  # model
            ),
            min_size=1,
            max_size=50
        )
    )
    @settings(max_examples=20)
    def test_complex_recording_operations(self, operations):
        """测试复杂的记录操作序列"""
        async def run_test():
            tracker = StatsTracker()
            tracker._initialized = True
            tracker._stats = {}
            
            # 记录所有操作
            expected_counts = {}
            for key_index, success, model in operations:
                await tracker.record_call(key_index, success, model)
                
                if key_index not in expected_counts:
                    expected_counts[key_index] = {"success": 0, "failure": 0}
                if success:
                    expected_counts[key_index]["success"] += 1
                else:
                    expected_counts[key_index]["failure"] += 1
            
            # 验证所有统计
            for key_index, expected in expected_counts.items():
                key_info = create_key_info(key_index)
                stats = await tracker.get_key_stats(key_index, key_info)
                
                assert stats.success_count == expected["success"], \
                    f"Key {key_index} success count mismatch"
                assert stats.failure_count == expected["failure"], \
                    f"Key {key_index} failure count mismatch"
        
        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
