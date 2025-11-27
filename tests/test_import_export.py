# Feature: api-key-management-enhancement, Property 25: 密钥导出完整性
# Feature: api-key-management-enhancement, Property 26: 密钥导入验证
# Feature: api-key-management-enhancement, Property 27: 密钥导入模式应用
# Feature: api-key-management-enhancement, Property 28: 密钥导入错误处理
"""
密钥导入导出属性测试
测试导入导出的完整性、验证和错误处理
"""
import pytest
import asyncio
from hypothesis import given, strategies as st, settings, assume, HealthCheck
from unittest.mock import AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.key_manager import KeyManager
from src.models_key import AggregationMode


class TestImportExport:
    """导入导出测试"""
    
    @pytest.fixture
    def key_manager(self):
        """创建密钥管理器实例"""
        manager = KeyManager()
        manager._initialized = True
        manager._cache = None
        manager._key_states = {}
        return manager
    
    # Feature: api-key-management-enhancement, Property 25: 密钥导出完整性
    # **Validates: Requirements 8.1**
    @given(
        keys=st.lists(
            st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=10,
            unique=True
        ),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=0, max_size=5, unique=True),
        mode=st.sampled_from(["round_robin", "random"]),
        calls_per_rotation=st.integers(min_value=1, max_value=1000)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_export_completeness(self, key_manager, keys, disabled_indices, mode, calls_per_rotation):
        """测试密钥导出完整性"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < len(keys)]
        
        async def run_test():
            with patch.object(key_manager, '_save_config', new_callable=AsyncMock):
                # 设置密钥
                await key_manager.add_keys(keys, "override")
                
                # 设置禁用索引
                for idx in valid_disabled:
                    await key_manager.update_key_status(idx, False)
                
                # 设置聚合模式
                await key_manager.set_aggregation_mode(AggregationMode(mode))
                
                # 设置轮换次数
                await key_manager.set_calls_per_rotation(calls_per_rotation)
                
                # 导出
                exported = await key_manager.export_keys()
                
                # 验证导出完整性
                assert "keys" in exported, "Export should contain 'keys'"
                assert "disabled_indices" in exported, "Export should contain 'disabled_indices'"
                assert "aggregation_mode" in exported, "Export should contain 'aggregation_mode'"
                assert "calls_per_rotation" in exported, "Export should contain 'calls_per_rotation'"
                
                # 验证数据正确
                assert exported["keys"] == keys, "Exported keys should match"
                assert set(exported["disabled_indices"]) == set(valid_disabled), "Exported disabled indices should match"
                assert exported["aggregation_mode"] == mode, "Exported mode should match"
                assert exported["calls_per_rotation"] == calls_per_rotation, "Exported calls per rotation should match"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 26: 密钥导入验证
    # **Validates: Requirements 8.2**
    @given(
        keys=st.lists(
            st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=10,
            unique=True
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_import_validation(self, key_manager, keys):
        """测试密钥导入验证"""
        async def run_test():
            with patch.object(key_manager, '_save_config', new_callable=AsyncMock):
                # 有效导入
                valid_config = {"keys": keys}
                success = await key_manager.import_keys(valid_config, "override")
                assert success, "Valid import should succeed"
                
                # 验证导入的密钥
                all_keys = await key_manager.get_all_keys()
                assert len(all_keys) == len(keys), "Imported key count should match"
                
                # 无效导入（空密钥列表）
                invalid_config = {"keys": []}
                success = await key_manager.import_keys(invalid_config, "override")
                assert not success, "Empty keys import should fail"
                
                # 无效导入（缺少 keys 字段）
                invalid_config = {"disabled_indices": [0]}
                success = await key_manager.import_keys(invalid_config, "override")
                assert not success, "Missing keys field should fail"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 27: 密钥导入模式应用
    # **Validates: Requirements 8.3**
    @given(
        initial_keys=st.lists(
            st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=5,
            unique=True
        ),
        new_keys=st.lists(
            st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=5,
            unique=True
        )
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_import_mode_application(self, key_manager, initial_keys, new_keys):
        """测试密钥导入模式应用"""
        async def run_test():
            with patch.object(key_manager, '_save_config', new_callable=AsyncMock):
                # 设置初始密钥
                await key_manager.add_keys(initial_keys, "override")
                
                # 测试追加模式
                append_config = {"keys": new_keys}
                success = await key_manager.import_keys(append_config, "append")
                assert success, "Append import should succeed"
                
                all_keys = await key_manager.get_all_keys()
                expected_count = len(initial_keys) + len(new_keys)
                assert len(all_keys) == expected_count, \
                    f"Append mode should have {expected_count} keys, got {len(all_keys)}"
                
                # 验证原有密钥保留
                for i, key in enumerate(initial_keys):
                    assert all_keys[i].key == key, f"Original key {i} should be preserved"
                
                # 测试覆盖模式
                override_config = {"keys": new_keys}
                success = await key_manager.import_keys(override_config, "override")
                assert success, "Override import should succeed"
                
                all_keys = await key_manager.get_all_keys()
                assert len(all_keys) == len(new_keys), \
                    f"Override mode should have {len(new_keys)} keys, got {len(all_keys)}"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    # Feature: api-key-management-enhancement, Property 28: 密钥导入错误处理
    # **Validates: Requirements 8.4**
    def test_import_error_handling(self, key_manager):
        """测试密钥导入错误处理"""
        async def run_test():
            with patch.object(key_manager, '_save_config', new_callable=AsyncMock):
                # 测试各种无效输入
                invalid_configs = [
                    {},  # 空配置
                    {"keys": []},  # 空密钥列表
                    {"keys": None},  # None 密钥
                    {"disabled_indices": [0]},  # 缺少 keys
                ]
                
                for config in invalid_configs:
                    success = await key_manager.import_keys(config, "override")
                    assert not success, f"Invalid config should fail: {config}"
                
                # 测试有效配置后的状态
                valid_config = {"keys": ["valid_key_1", "valid_key_2"]}
                success = await key_manager.import_keys(valid_config, "override")
                assert success, "Valid config should succeed"
                
                all_keys = await key_manager.get_all_keys()
                assert len(all_keys) == 2, "Should have 2 keys after valid import"
        
        asyncio.get_event_loop().run_until_complete(run_test())
    
    @given(
        keys=st.lists(
            st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
            min_size=1,
            max_size=10,
            unique=True
        ),
        disabled_indices=st.lists(st.integers(min_value=0, max_value=9), min_size=0, max_size=5, unique=True)
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_export_import_round_trip(self, key_manager, keys, disabled_indices):
        """测试导出导入往返一致性"""
        # 过滤有效的禁用索引
        valid_disabled = [i for i in disabled_indices if i < len(keys)]
        
        async def run_test():
            with patch.object(key_manager, '_save_config', new_callable=AsyncMock):
                # 设置初始状态
                await key_manager.add_keys(keys, "override")
                for idx in valid_disabled:
                    await key_manager.update_key_status(idx, False)
                
                # 导出
                exported = await key_manager.export_keys()
                
                # 清空并导入
                await key_manager.add_keys(["temp"], "override")
                success = await key_manager.import_keys(exported, "override")
                assert success, "Import should succeed"
                
                # 验证往返一致性
                all_keys = await key_manager.get_all_keys()
                assert len(all_keys) == len(keys), "Key count should match after round trip"
                
                for i, key_info in enumerate(all_keys):
                    assert key_info.key == keys[i], f"Key {i} should match after round trip"
                    expected_enabled = i not in valid_disabled
                    assert key_info.enabled == expected_enabled, \
                        f"Key {i} enabled status should match after round trip"
        
        asyncio.get_event_loop().run_until_complete(run_test())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
