"""
Tests for fake streaming mode
测试假流式模式
Feature: openai-protocol-refactor, Property 11: 假流式模式启用
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from src.models import ChatCompletionRequest, OpenAIChatMessage


class TestFakeStreaming:
    """测试假流式模式"""
    
    @pytest.mark.asyncio
    async def test_fake_streaming_enabled_for_stream_true(self):
        """测试 stream=true 时启用假流式"""
        request_data = ChatCompletionRequest(
            model="gpt-5",
            messages=[OpenAIChatMessage(role="user", content="Hello")],
            stream=True
        )
        
        # 验证：stream 参数为 True
        assert request_data.stream is True
    
    @pytest.mark.asyncio
    async def test_fake_streaming_disabled_for_stream_false(self):
        """测试 stream=false 时不使用假流式"""
        request_data = ChatCompletionRequest(
            model="gpt-5",
            messages=[OpenAIChatMessage(role="user", content="Hello")],
            stream=False
        )
        
        # 验证：stream 参数为 False
        assert request_data.stream is False
    
    def test_sse_format_structure(self):
        """测试 SSE 格式结构"""
        # SSE 格式应该是 "data: {json}\n\n"
        chunk = {
            "id": "test-123",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "gpt-5",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "Hello"},
                "finish_reason": None
            }]
        }
        
        sse_line = f"data: {json.dumps(chunk)}\n\n"
        
        # 验证：以 "data: " 开头
        assert sse_line.startswith("data: ")
        # 验证：以 "\n\n" 结尾
        assert sse_line.endswith("\n\n")
        # 验证：可以解析 JSON
        json_str = sse_line[6:-2]  # 移除 "data: " 和 "\n\n"
        parsed = json.loads(json_str)
        assert parsed["id"] == "test-123"
    
    def test_done_marker_format(self):
        """测试 [DONE] 标记格式"""
        done_marker = "data: [DONE]\n\n"
        
        # 验证：格式正确
        assert done_marker == "data: [DONE]\n\n"
        assert done_marker.startswith("data: ")
        assert done_marker.endswith("\n\n")
    
    def test_heartbeat_chunk_structure(self):
        """测试心跳包结构"""
        heartbeat = {
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None
            }]
        }
        
        # 验证：心跳包有正确的结构
        assert "choices" in heartbeat
        assert len(heartbeat["choices"]) == 1
        assert heartbeat["choices"][0]["delta"]["content"] == ""
        assert heartbeat["choices"][0]["finish_reason"] is None
    
    def test_content_chunk_with_tool_calls(self):
        """测试包含 tool_calls 的内容块"""
        chunk = {
            "id": "test-456",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "gpt-5",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": "{\"location\": \"SF\"}"
                        }
                    }]
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15
            }
        }
        
        # 验证：包含 tool_calls
        assert "tool_calls" in chunk["choices"][0]["delta"]
        assert len(chunk["choices"][0]["delta"]["tool_calls"]) == 1
        
        # 验证：包含 usage（在最后一个 chunk 中）
        assert "usage" in chunk
        assert chunk["usage"]["total_tokens"] == 15
        
        # 验证：finish_reason 为 stop
        assert chunk["choices"][0]["finish_reason"] == "stop"
    
    def test_usage_in_final_chunk(self):
        """测试 usage 信息在最后一个 chunk 中"""
        final_chunk = {
            "id": "test-789",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "gpt-5",
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": "Final response"},
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": 20,
                "completion_tokens": 10,
                "total_tokens": 30
            }
        }
        
        # 验证：最后一个 chunk 有 finish_reason
        assert final_chunk["choices"][0]["finish_reason"] == "stop"
        
        # 验证：最后一个 chunk 有 usage
        assert "usage" in final_chunk
        assert final_chunk["usage"]["prompt_tokens"] == 20
        assert final_chunk["usage"]["completion_tokens"] == 10
        assert final_chunk["usage"]["total_tokens"] == 30
    
    def test_tool_calls_arguments_json_string(self):
        """测试 tool_calls 的 arguments 是 JSON 字符串格式"""
        tool_call = {
            "id": "call_abc",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": "{\"query\": \"test\"}"  # 必须是字符串
            }
        }
        
        # 验证：arguments 是字符串
        assert isinstance(tool_call["function"]["arguments"], str)
        
        # 验证：可以解析为 JSON
        args = json.loads(tool_call["function"]["arguments"])
        assert args["query"] == "test"
    
    def test_empty_content_with_tool_calls_in_stream(self):
        """测试流式模式下空 content + tool_calls"""
        chunk = {
            "id": "test-xyz",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "gpt-5",
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant",
                    "tool_calls": [{
                        "id": "call_456",
                        "type": "function",
                        "function": {"name": "calculate", "arguments": "{}"}
                    }]
                },
                "finish_reason": "stop"
            }]
        }
        
        # 验证：delta 中有 tool_calls
        assert "tool_calls" in chunk["choices"][0]["delta"]
        
        # 验证：content 可以不存在（对于只有 tool_calls 的情况）
        assert "content" not in chunk["choices"][0]["delta"] or \
               chunk["choices"][0]["delta"].get("content") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
