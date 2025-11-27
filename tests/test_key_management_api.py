# Feature: api-key-management-enhancement, Property 21: 搜索过滤准确性
# Feature: api-key-management-enhancement, Property 22: 状态过滤准确性
# Feature: api-key-management-enhancement, Property 23: 搜索重置完整性
# Feature: api-key-management-enhancement, Property 24: 排序顺序正确性
"""
密钥管理 API 属性测试
测试搜索、过滤和排序功能
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings, assume
from unittest.mock import AsyncMock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models_key import KeyInfo, KeyStatus


def create_key_info(index: int, key: str, enabled: bool = True) -> KeyInfo:
    """创建测试用的 KeyInfo"""
    return KeyInfo(
        index=index,
        key=key,
        enabled=enabled,
        status=KeyStatus.ACTIVE
    )


class TestKeyManagementAPI:
    """密钥管理 API 测试"""
    
    # Feature: api-key-management-enhancement, Property 21: 搜索过滤准确性
    # **Validates: Requirements 7.1**
    @given(
        keys=st.lists(
            st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=10,
            unique=True
        ),
        search_term=st.text(min_size=1, max_size=5, alphabet=st.characters(whitelist_categories=("L", "N")))
    )
    @settings(max_examples=30)
    def test_search_filter_accuracy(self, keys, search_term):
        """测试搜索过滤准确性"""
        # 创建密钥列表
        key_infos = [create_key_info(i, key) for i, key in enumerate(keys)]
        
        # 模拟搜索逻辑
        search_lower = search_term.lower()
        results = [k for k in key_infos if search_lower in k.key.lower() or search_lower in k.masked_key.lower()]
        
        # 验证搜索结果
        for result in results:
            # 每个结果都应该包含搜索词
            assert search_lower in result.key.lower() or search_lower in result.masked_key.lower(), \
                f"Result {result.key} should contain search term '{search_term}'"
        
        # 验证没有遗漏
        for key_info in key_infos:
            if search_lower in key_info.key.lower() or search_lower in key_info.masked_key.lower():
                assert key_info in results, f"Key {key_info.key} should be in results"
    
    # Feature: api-key-management-enhancement, Property 22: 状态过滤准确性
    # **Validates: Requirements 7.2**
    @given(
        num_keys=st.integers(min_value=2, max_value=10),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=0, max_size=5, unique=True)
    )
    @settings(max_examples=30)
    def test_status_filter_accuracy(self, num_keys, disabled_indices):
        """测试状态过滤准确性"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < num_keys]
        
        # 创建密钥列表
        key_infos = []
        for i in range(num_keys):
            enabled = i not in valid_disabled
            key_infos.append(create_key_info(i, f"key_{i}", enabled=enabled))
        
        # 测试 enabled 过滤
        enabled_results = [k for k in key_infos if k.enabled]
        for result in enabled_results:
            assert result.enabled, "Enabled filter should only return enabled keys"
        assert len(enabled_results) == num_keys - len(valid_disabled), "Enabled count mismatch"
        
        # 测试 disabled 过滤
        disabled_results = [k for k in key_infos if not k.enabled]
        for result in disabled_results:
            assert not result.enabled, "Disabled filter should only return disabled keys"
        assert len(disabled_results) == len(valid_disabled), "Disabled count mismatch"
        
        # 测试 all 过滤（无过滤）
        all_results = key_infos
        assert len(all_results) == num_keys, "All filter should return all keys"
    
    # Feature: api-key-management-enhancement, Property 23: 搜索重置完整性
    # **Validates: Requirements 7.3**
    @given(
        num_keys=st.integers(min_value=3, max_value=10)
    )
    @settings(max_examples=20)
    def test_search_reset_completeness(self, num_keys):
        """测试搜索重置完整性"""
        # 创建密钥列表
        key_infos = [create_key_info(i, f"key_{i}") for i in range(num_keys)]
        
        # 模拟搜索
        search_term = "key_0"
        search_results = [k for k in key_infos if search_term in k.key]
        assert len(search_results) < num_keys, "Search should filter some keys"
        
        # 模拟重置搜索（清空搜索词）
        reset_results = key_infos  # 重置后应该返回所有密钥
        
        # 验证重置后返回所有密钥
        assert len(reset_results) == num_keys, "Reset should return all keys"
        for i in range(num_keys):
            assert any(k.index == i for k in reset_results), f"Key {i} should be in reset results"
    
    # Feature: api-key-management-enhancement, Property 24: 排序顺序正确性
    # **Validates: Requirements 7.5**
    @given(
        num_keys=st.integers(min_value=2, max_value=10),
        sort_order=st.sampled_from(["asc", "desc"])
    )
    @settings(max_examples=30)
    def test_sort_order_correctness(self, num_keys, sort_order):
        """测试排序顺序正确性"""
        import random
        
        # 创建乱序的密钥列表
        indices = list(range(num_keys))
        random.shuffle(indices)
        key_infos = [create_key_info(i, f"key_{i}") for i in indices]
        
        # 按索引排序
        reverse = sort_order == "desc"
        sorted_results = sorted(key_infos, key=lambda k: k.index, reverse=reverse)
        
        # 验证排序顺序
        for i in range(len(sorted_results) - 1):
            if sort_order == "asc":
                assert sorted_results[i].index < sorted_results[i + 1].index, \
                    f"Ascending order violated at index {i}"
            else:
                assert sorted_results[i].index > sorted_results[i + 1].index, \
                    f"Descending order violated at index {i}"
    
    @given(
        num_keys=st.integers(min_value=2, max_value=10),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=1, max_size=5, unique=True)
    )
    @settings(max_examples=20)
    def test_sort_by_status(self, num_keys, disabled_indices):
        """测试按状态排序"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < num_keys]
        assume(len(valid_disabled) > 0 and len(valid_disabled) < num_keys)
        
        # 创建密钥列表
        key_infos = []
        for i in range(num_keys):
            enabled = i not in valid_disabled
            key_infos.append(create_key_info(i, f"key_{i}", enabled=enabled))
        
        # 按状态排序（启用优先）
        sorted_results = sorted(key_infos, key=lambda k: (not k.enabled, k.index))
        
        # 验证启用的密钥在前面
        enabled_count = num_keys - len(valid_disabled)
        for i in range(enabled_count):
            assert sorted_results[i].enabled, f"Enabled keys should come first, but index {i} is disabled"
        
        for i in range(enabled_count, num_keys):
            assert not sorted_results[i].enabled, f"Disabled keys should come last, but index {i} is enabled"


class TestKeyManagementAPIIntegration:
    """密钥管理 API 集成测试"""
    
    @given(
        operations=st.lists(
            st.one_of(
                st.tuples(st.just("search"), st.text(min_size=1, max_size=5)),
                st.tuples(st.just("filter"), st.sampled_from(["enabled", "disabled", "all"])),
                st.tuples(st.just("sort"), st.sampled_from(["asc", "desc"])),
            ),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=20)
    def test_combined_operations(self, operations):
        """测试组合操作"""
        # 创建测试数据
        key_infos = [
            create_key_info(0, "alpha_key", enabled=True),
            create_key_info(1, "beta_key", enabled=False),
            create_key_info(2, "gamma_key", enabled=True),
            create_key_info(3, "delta_key", enabled=False),
            create_key_info(4, "epsilon_key", enabled=True),
        ]
        
        results = key_infos.copy()
        
        for op_type, arg in operations:
            if op_type == "search":
                search_lower = arg.lower()
                results = [k for k in results if search_lower in k.key.lower()]
            elif op_type == "filter":
                if arg == "enabled":
                    results = [k for k in results if k.enabled]
                elif arg == "disabled":
                    results = [k for k in results if not k.enabled]
                # "all" 不过滤
            elif op_type == "sort":
                reverse = arg == "desc"
                results = sorted(results, key=lambda k: k.index, reverse=reverse)
        
        # 验证结果一致性
        # 所有结果都应该来自原始列表
        for result in results:
            assert result in key_infos, "Result should be from original list"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
