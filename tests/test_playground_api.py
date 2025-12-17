# Feature: api-key-management-enhancement, Property 33: 自定义报文使用
# Feature: api-key-management-enhancement, Property 34: 自定义报文状态恢复
"""
操练场 API 属性测试
测试自定义报文使用和状态恢复
"""
import pytest
import json
from hypothesis import given, strategies as st, settings, HealthCheck

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.transform.request_generator import RequestGenerator


class TestPlaygroundAPI:
    """操练场 API 测试"""
    
    @pytest.fixture
    def generator(self):
        """创建请求生成器实例"""
        return RequestGenerator(
            endpoint="https://api.example.com/v1/chat/completions",
            api_key="sk-test-key"
        )
    
    # Feature: api-key-management-enhancement, Property 33: 自定义报文使用
    # **Validates: Requirements 10.5**
    @given(
        model=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
        content=st.text(min_size=1, max_size=100),
        temperature=st.floats(min_value=0, max_value=2)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_custom_request_usage(self, generator, model, content, temperature):
        """测试自定义报文使用"""
        # 生成初始请求
        params = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
        }
        
        initial_json = generator.generate_initial_custom_request(params)
        
        # 验证初始请求有效
        is_valid, error = generator.validate_custom_request(initial_json)
        assert is_valid, f"Initial request should be valid: {error}"
        
        # 解析并修改请求
        parsed = json.loads(initial_json)
        parsed["temperature"] = 0.5  # 修改温度
        modified_json = json.dumps(parsed)
        
        # 验证修改后的请求仍然有效
        is_valid, error = generator.validate_custom_request(modified_json)
        assert is_valid, f"Modified request should be valid: {error}"
        
        # 解析修改后的请求
        final_parsed = generator.parse_custom_request(modified_json)
        assert final_parsed is not None, "Should be able to parse modified request"
        assert final_parsed["temperature"] == 0.5, "Modified temperature should be preserved"
    
    # Feature: api-key-management-enhancement, Property 34: 自定义报文状态恢复
    # **Validates: Requirements 10.7**
    @given(
        model=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))),
        content=st.text(min_size=1, max_size=100),
        temperature=st.floats(min_value=0, max_value=2),
        max_tokens=st.integers(min_value=1, max_value=4096)
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_custom_request_state_recovery(self, generator, model, content, temperature, max_tokens):
        """测试自定义报文状态恢复"""
        # 原始参数
        original_params = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # 生成初始请求
        initial_json = generator.generate_initial_custom_request(original_params)
        
        # 模拟用户修改
        parsed = json.loads(initial_json)
        parsed["temperature"] = 1.0
        parsed["max_tokens"] = 2000
        modified_json = json.dumps(parsed)
        
        # 模拟"恢复默认"操作 - 重新生成初始请求
        recovered_json = generator.generate_initial_custom_request(original_params)
        
        # 验证恢复后的请求与原始一致
        recovered_parsed = json.loads(recovered_json)
        assert recovered_parsed["model"] == model, "Model should be recovered"
        assert recovered_parsed["messages"][0]["content"] == content, "Content should be recovered"
        assert recovered_parsed["temperature"] == temperature, "Temperature should be recovered"
        assert recovered_parsed["max_tokens"] == max_tokens, "Max tokens should be recovered"
    
    def test_preview_generation(self, generator):
        """测试预览生成"""
        params = {
            "model": "gpt-4",
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.7,
            "max_tokens": 1000,
        }
        
        preview = generator.generate_request_preview(params)
        
        # 验证预览包含所有必需信息
        assert preview["method"] == "POST"
        assert preview["url"] == generator._endpoint
        assert "Authorization" in preview["headers"]
        assert preview["body"]["model"] == "gpt-4"
        assert preview["body"]["temperature"] == 0.7
        
        # 验证 JSON 格式正确
        parsed = json.loads(preview["body_json"])
        assert parsed == preview["body"]
    
    def test_validation_error_messages(self, generator):
        """测试验证错误消息"""
        test_cases = [
            ('{}', "Missing required field: model"),
            ('{"model": "gpt-4"}', "Missing required field: messages"),
            ('{"model": "gpt-4", "messages": []}', "Field 'messages' cannot be empty"),
        ]
        
        for request_json, expected_error in test_cases:
            is_valid, error = generator.validate_custom_request(request_json)
            assert not is_valid, f"Should be invalid: {request_json}"
            assert expected_error in error, f"Error should contain '{expected_error}', got '{error}'"


class TestPlaygroundAPIIntegration:
    """操练场 API 集成测试"""
    
    @given(
        operations=st.lists(
            st.one_of(
                st.tuples(st.just("generate"), st.text(min_size=1, max_size=20)),
                st.tuples(st.just("modify"), st.floats(min_value=0, max_value=2)),
                st.tuples(st.just("validate"), st.just(None)),
            ),
            min_size=1,
            max_size=10
        )
    )
    @settings(max_examples=20)
    def test_complex_playground_operations(self, operations):
        """测试复杂的操练场操作序列"""
        generator = RequestGenerator(
            endpoint="https://api.example.com/v1/chat/completions",
            api_key="sk-test"
        )
        
        current_json = None
        
        for op_type, arg in operations:
            try:
                if op_type == "generate":
                    params = {
                        "model": arg if arg else "gpt-4",
                        "messages": [{"role": "user", "content": "test"}],
                    }
                    current_json = generator.generate_initial_custom_request(params)
                elif op_type == "modify" and current_json:
                    parsed = json.loads(current_json)
                    parsed["temperature"] = arg
                    current_json = json.dumps(parsed)
                elif op_type == "validate" and current_json:
                    is_valid, _ = generator.validate_custom_request(current_json)
                    # 验证应该总是成功（因为我们只做有效的修改）
                    assert is_valid, "Validation should pass for valid modifications"
            except Exception:
                pass
        
        # 最终状态应该是有效的（如果有的话）
        if current_json:
            is_valid, error = generator.validate_custom_request(current_json)
            assert is_valid, f"Final state should be valid: {error}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
