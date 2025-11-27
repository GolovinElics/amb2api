"""
Property-based tests for empty content with tool_calls preservation
属性测试：空 content 但有 tool_calls 的消息保留
Feature: openai-protocol-refactor, Property 7: 空 content 但有 tool_calls 的消息保留
"""
import pytest
from hypothesis import given, settings, strategies as st
from src.models import OpenAIChatMessage
from src.assembly_client import _sanitize_messages


@st.composite
def message_with_tool_calls_strategy(draw):
    """生成带 tool_calls 的消息"""
    # content 可能为空或 None
    content = draw(st.one_of(
        st.none(),
        st.just(""),
        st.text(min_size=0, max_size=50)
    ))
    
    num_calls = draw(st.integers(min_value=1, max_value=3))
    tool_calls = []
    for _ in range(num_calls):
        tool_calls.append({
            "id": f"call_{draw(st.integers(min_value=1, max_value=9999))}",
            "type": "function",
            "function": {
                "name": draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("Lu", "Ll")))),
                "arguments": draw(st.sampled_from(['{}', '{"param": "value"}', '{"x": 1}']))
            }
        })
    
    return OpenAIChatMessage(
        role="assistant",
        content=content,
        tool_calls=tool_calls
    )


class TestEmptyContentPreservation:
    """测试空 content 但有 tool_calls 的消息保留"""
    
    @given(message_with_tool_calls_strategy())
    @settings(max_examples=100)
    def test_property_empty_content_with_tool_calls(self, message):
        """
        Property 7: 空 content 但有 tool_calls 的消息保留
        For any content 为空但包含 tool_calls 的消息，系统应该保留该消息
        """
        sanitized = _sanitize_messages([message])
        
        # 验证：消息被保留
        assert len(sanitized) == 1
        
        # 验证：tool_calls 被保留
        assert "tool_calls" in sanitized[0]
        assert len(sanitized[0]["tool_calls"]) == len(message.tool_calls)
        
        # 验证：tool_calls 内容正确
        for i, (original_call, sanitized_call) in enumerate(zip(message.tool_calls, sanitized[0]["tool_calls"])):
            assert sanitized_call["id"] == original_call["id"]
            assert sanitized_call["type"] == original_call["type"]
            assert sanitized_call["function"]["name"] == original_call["function"]["name"]
    
    def test_none_content_with_tool_calls(self):
        """测试 content=None 但有 tool_calls"""
        message = OpenAIChatMessage(
            role="assistant",
            content=None,
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": "{}"}
            }]
        )
        
        sanitized = _sanitize_messages([message])
        
        assert len(sanitized) == 1
        assert sanitized[0]["role"] == "assistant"
        assert "tool_calls" in sanitized[0]
        assert len(sanitized[0]["tool_calls"]) == 1
    
    def test_empty_string_content_with_tool_calls(self):
        """测试 content="" 但有 tool_calls"""
        message = OpenAIChatMessage(
            role="assistant",
            content="",
            tool_calls=[{
                "id": "call_456",
                "type": "function",
                "function": {"name": "search", "arguments": '{"query": "test"}'}
            }]
        )
        
        sanitized = _sanitize_messages([message])
        
        assert len(sanitized) == 1
        assert sanitized[0]["role"] == "assistant"
        assert sanitized[0]["content"] == ""
        assert "tool_calls" in sanitized[0]
    
    def test_multiple_tool_calls_empty_content(self):
        """测试多个 tool_calls 且 content 为空"""
        message = OpenAIChatMessage(
            role="assistant",
            content=None,
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "func1", "arguments": "{}"}
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "func2", "arguments": "{}"}
                },
                {
                    "id": "call_3",
                    "type": "function",
                    "function": {"name": "func3", "arguments": "{}"}
                }
            ]
        )
        
        sanitized = _sanitize_messages([message])
        
        assert len(sanitized) == 1
        assert "tool_calls" in sanitized[0]
        assert len(sanitized[0]["tool_calls"]) == 3
        
        # 验证所有 tool_calls 都被保留
        for i in range(3):
            assert sanitized[0]["tool_calls"][i]["id"] == f"call_{i+1}"
    
    def test_mixed_messages_with_empty_content_tool_calls(self):
        """测试混合消息，包含空 content + tool_calls 的消息"""
        messages = [
            OpenAIChatMessage(role="user", content="Hello"),
            OpenAIChatMessage(
                role="assistant",
                content=None,
                tool_calls=[{
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "search", "arguments": "{}"}
                }]
            ),
            OpenAIChatMessage(
                role="tool",
                content="Search result",
                tool_call_id="call_123"
            ),
            OpenAIChatMessage(role="assistant", content="Here's the answer")
        ]
        
        sanitized = _sanitize_messages(messages)
        
        # 验证所有消息都被保留
        assert len(sanitized) == 4
        
        # 验证第二条消息（空 content + tool_calls）被正确保留
        assert sanitized[1]["role"] == "assistant"
        assert "tool_calls" in sanitized[1]
        assert sanitized[1]["tool_calls"][0]["id"] == "call_123"
        
        # 验证 tool 消息也被保留
        assert sanitized[2]["role"] == "tool"
        assert sanitized[2]["tool_call_id"] == "call_123"
    
    def test_whitespace_content_with_tool_calls(self):
        """测试仅包含空白字符的 content + tool_calls"""
        message = OpenAIChatMessage(
            role="assistant",
            content="   ",
            tool_calls=[{
                "id": "call_789",
                "type": "function",
                "function": {"name": "calculate", "arguments": '{"x": 5}'}
            }]
        )
        
        sanitized = _sanitize_messages([message])
        
        assert len(sanitized) == 1
        assert "tool_calls" in sanitized[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
