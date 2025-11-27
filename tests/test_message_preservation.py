"""
Property-based tests for message order preservation
属性测试：消息顺序保持
Feature: openai-protocol-refactor, Property 5: 消息顺序保持
"""
import pytest
from hypothesis import given, settings, strategies as st
from src.models import OpenAIChatMessage
from src.assembly_client import _sanitize_messages


@st.composite
def message_with_role_strategy(draw, role):
    """生成指定角色的消息"""
    content = draw(st.text(min_size=1, max_size=100))
    message_dict = {"role": role, "content": content}
    
    if role == "assistant" and draw(st.booleans()):
        message_dict["tool_calls"] = [{
            "id": f"call_{draw(st.integers(min_value=1, max_value=999))}",
            "type": "function",
            "function": {"name": "test_func", "arguments": "{}"}
        }]
    
    if role == "tool":
        message_dict["tool_call_id"] = f"call_{draw(st.integers(min_value=1, max_value=999))}"
    
    return OpenAIChatMessage(**message_dict)


@st.composite
def message_list_strategy(draw):
    """生成包含多种角色的消息列表"""
    num_messages = draw(st.integers(min_value=2, max_value=20))
    messages = []
    
    for _ in range(num_messages):
        role = draw(st.sampled_from(["user", "assistant", "system", "tool"]))
        messages.append(draw(message_with_role_strategy(role)))
    
    return messages


class TestMessagePreservation:
    """测试消息顺序保持"""
    
    @given(message_list_strategy())
    @settings(max_examples=100)
    def test_property_message_order_preserved(self, messages):
        """
        Property 5: 消息顺序保持
        For any 包含多条消息的请求，系统应该按原始顺序保留所有消息
        （包括 user、assistant、system、tool 角色）
        """
        sanitized = _sanitize_messages(messages)
        
        # 验证：消息数量不变
        assert len(sanitized) == len(messages)
        
        # 验证：顺序保持不变
        for i, (original, sanitized_msg) in enumerate(zip(messages, sanitized)):
            assert sanitized_msg["role"] == original.role, f"Message {i}: role order changed"
            
            # 验证内容也保持顺序
            if original.content:
                assert sanitized_msg["content"] == original.content, f"Message {i}: content changed"
    
    @given(st.lists(message_with_role_strategy("user"), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_user_messages_order(self, messages):
        """测试 user 消息顺序保持"""
        sanitized = _sanitize_messages(messages)
        
        for i, (original, sanitized_msg) in enumerate(zip(messages, sanitized)):
            assert sanitized_msg["role"] == "user"
            assert sanitized_msg["content"] == original.content
    
    @given(st.lists(message_with_role_strategy("assistant"), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_assistant_messages_order(self, messages):
        """测试 assistant 消息顺序保持"""
        sanitized = _sanitize_messages(messages)
        
        for i, (original, sanitized_msg) in enumerate(zip(messages, sanitized)):
            assert sanitized_msg["role"] == "assistant"
    
    @given(st.lists(message_with_role_strategy("system"), min_size=1, max_size=5))
    @settings(max_examples=50)
    def test_system_messages_order(self, messages):
        """测试 system 消息顺序保持"""
        sanitized = _sanitize_messages(messages)
        
        for i, (original, sanitized_msg) in enumerate(zip(messages, sanitized)):
            assert sanitized_msg["role"] == "system"
            assert sanitized_msg["content"] == original.content
    
    @given(st.lists(message_with_role_strategy("tool"), min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_tool_messages_order(self, messages):
        """测试 tool 消息顺序保持"""
        sanitized = _sanitize_messages(messages)
        
        for i, (original, sanitized_msg) in enumerate(zip(messages, sanitized)):
            assert sanitized_msg["role"] == "tool"
            # tool 消息应该保留 tool_call_id
            if original.tool_call_id:
                assert "tool_call_id" in sanitized_msg
    
    def test_mixed_roles_order(self):
        """测试混合角色的消息顺序"""
        messages = [
            OpenAIChatMessage(role="system", content="System prompt"),
            OpenAIChatMessage(role="user", content="User message 1"),
            OpenAIChatMessage(role="assistant", content="Assistant response 1"),
            OpenAIChatMessage(role="user", content="User message 2"),
            OpenAIChatMessage(role="assistant", content=None, tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {"name": "search", "arguments": "{}"}
            }]),
            OpenAIChatMessage(role="tool", content="Tool result", tool_call_id="call_123"),
            OpenAIChatMessage(role="assistant", content="Final response"),
        ]
        
        sanitized = _sanitize_messages(messages)
        
        # 验证顺序
        assert len(sanitized) == 7
        assert sanitized[0]["role"] == "system"
        assert sanitized[1]["role"] == "user"
        assert sanitized[2]["role"] == "assistant"
        assert sanitized[3]["role"] == "user"
        assert sanitized[4]["role"] == "assistant"
        assert sanitized[5]["role"] == "tool"
        assert sanitized[6]["role"] == "assistant"
        
        # 验证内容
        assert sanitized[0]["content"] == "System prompt"
        assert sanitized[1]["content"] == "User message 1"
        assert sanitized[5]["content"] == "Tool result"
        assert sanitized[6]["content"] == "Final response"
        
        # 验证 tool_calls 和 tool_call_id
        assert "tool_calls" in sanitized[4]
        assert "tool_call_id" in sanitized[5]
        assert sanitized[5]["tool_call_id"] == "call_123"
    
    def test_empty_list(self):
        """测试空消息列表"""
        sanitized = _sanitize_messages([])
        assert len(sanitized) == 0
    
    def test_single_message(self):
        """测试单条消息"""
        message = OpenAIChatMessage(role="user", content="Hello")
        sanitized = _sanitize_messages([message])
        
        assert len(sanitized) == 1
        assert sanitized[0]["role"] == "user"
        assert sanitized[0]["content"] == "Hello"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
