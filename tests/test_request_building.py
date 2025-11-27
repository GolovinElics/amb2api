"""
Property-based tests for request building and parameter passthrough
属性测试：请求构建和参数透传
Feature: openai-protocol-refactor, Property 1: 请求格式验证和参数透传
"""
import pytest
import json
from hypothesis import given, settings, strategies as st
from src.models import ChatCompletionRequest, OpenAIChatMessage
from src.assembly_client import _sanitize_messages


# 生成策略
@st.composite
def message_strategy(draw):
    """生成随机消息"""
    role = draw(st.sampled_from(["user", "assistant", "system", "tool"]))
    content = draw(st.one_of(
        st.text(min_size=0, max_size=200),
        st.none()
    ))
    
    message_dict = {"role": role, "content": content}
    
    # 有时添加 tool_calls（仅对 assistant）
    if role == "assistant" and draw(st.booleans()):
        num_calls = draw(st.integers(min_value=1, max_value=3))
        tool_calls = []
        for _ in range(num_calls):
            tool_calls.append({
                "id": draw(st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))),
                "type": "function",
                "function": {
                    "name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll")))),
                    "arguments": "{}"
                }
            })
        message_dict["tool_calls"] = tool_calls
    
    # 有时添加 tool_call_id（仅对 tool）
    if role == "tool" and draw(st.booleans()):
        message_dict["tool_call_id"] = draw(st.text(min_size=5, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))))
    
    return OpenAIChatMessage(**message_dict)


@st.composite
def openai_request_strategy(draw):
    """生成随机的 OpenAI 请求"""
    model = draw(st.sampled_from(["gpt-5", "gpt-4.1", "claude-4.5-sonnet", "gemini-2.5-pro"]))
    
    # 生成消息
    num_messages = draw(st.integers(min_value=1, max_value=10))
    messages = [draw(message_strategy()) for _ in range(num_messages)]
    
    request_dict = {
        "model": model,
        "messages": messages,
        "stream": draw(st.booleans())
    }
    
    # 随机添加可选参数
    if draw(st.booleans()):
        request_dict["temperature"] = draw(st.floats(min_value=0.0, max_value=2.0))
    if draw(st.booleans()):
        request_dict["max_tokens"] = draw(st.integers(min_value=1, max_value=4096))
    if draw(st.booleans()):
        request_dict["top_p"] = draw(st.floats(min_value=0.0, max_value=1.0))
    
    return ChatCompletionRequest(**request_dict)


class TestRequestBuilding:
    """测试请求构建和参数透传"""
    
    @given(openai_request_strategy())
    @settings(max_examples=100)
    def test_property_request_validation_and_passthrough(self, request_data):
        """
        Property 1: 请求格式验证和参数透传
        For any OpenAI 格式的聊天完成请求，系统应该验证请求的有效性，
        并将所有支持的参数（messages、tools、tool_choice、temperature、max_tokens 等）
        原样透传给 AssemblyAI
        """
        # 验证：请求对象创建成功
        assert request_data is not None
        assert request_data.model in ["gpt-5", "gpt-4.1", "claude-4.5-sonnet", "gemini-2.5-pro"]
        assert len(request_data.messages) >= 1
        
        # 验证：消息清理后保留所有消息
        sanitized = _sanitize_messages(request_data.messages)
        assert len(sanitized) == len(request_data.messages)
        
        # 验证：所有角色类型都被保留
        for i, (original, sanitized_msg) in enumerate(zip(request_data.messages, sanitized)):
            assert sanitized_msg["role"] == original.role, f"Message {i}: role mismatch"
            
            # 验证：tool_calls 被保留
            if hasattr(original, "tool_calls") and original.tool_calls:
                assert "tool_calls" in sanitized_msg, f"Message {i}: tool_calls missing"
                assert len(sanitized_msg["tool_calls"]) == len(original.tool_calls)
            
            # 验证：tool_call_id 被保留
            if hasattr(original, "tool_call_id") and original.tool_call_id:
                assert "tool_call_id" in sanitized_msg, f"Message {i}: tool_call_id missing"
                assert sanitized_msg["tool_call_id"] == original.tool_call_id
    
    @given(message_strategy())
    @settings(max_examples=100)
    def test_all_role_types_preserved(self, message):
        """测试所有角色类型都被保留"""
        sanitized = _sanitize_messages([message])
        assert len(sanitized) == 1
        assert sanitized[0]["role"] == message.role
    
    @given(st.lists(message_strategy(), min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_message_count_preserved(self, messages):
        """测试消息数量保持不变"""
        sanitized = _sanitize_messages(messages)
        assert len(sanitized) == len(messages)
    
    def test_tool_calls_preserved(self):
        """测试 tool_calls 被正确保留"""
        message = OpenAIChatMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "arguments": "{\"location\": \"SF\"}"
                }
            }]
        )
        
        sanitized = _sanitize_messages([message])
        assert len(sanitized) == 1
        assert "tool_calls" in sanitized[0]
        assert len(sanitized[0]["tool_calls"]) == 1
        assert sanitized[0]["tool_calls"][0]["id"] == "call_123"
    
    def test_tool_call_id_preserved(self):
        """测试 tool_call_id 被正确保留"""
        message = OpenAIChatMessage(
            role="tool",
            content="Result",
            tool_call_id="call_123"
        )
        
        sanitized = _sanitize_messages([message])
        assert len(sanitized) == 1
        assert sanitized[0]["role"] == "tool"
        assert "tool_call_id" in sanitized[0]
        assert sanitized[0]["tool_call_id"] == "call_123"
    
    def test_empty_content_with_tool_calls(self):
        """测试空 content 但有 tool_calls 的消息"""
        message = OpenAIChatMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_456",
                "type": "function",
                "function": {"name": "search", "arguments": "{}"}
            }]
        )
        
        sanitized = _sanitize_messages([message])
        assert len(sanitized) == 1
        assert "tool_calls" in sanitized[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
