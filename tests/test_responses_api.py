import asyncio
import json
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from src.api import openai_router


class _Trace:
    def __init__(self, trace_id):
        self.trace_id = trace_id
        self.model = "pending"
        self.metadata = {}

    def mark(self, _):
        return None


class _Tracker:
    def start_trace(self, trace_id, _):
        return _Trace(trace_id)

    async def end_trace(self, *args, **kwargs):
        return None


async def _auth_override():
    return "ok"


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(openai_router.router)
    app.dependency_overrides[openai_router.authenticate] = _auth_override
    return app


def test_json_request_proxy_delegates_request_attributes():
    class DummyRequest:
        def __init__(self):
            self.state = object()
            self.headers = {"x-test": "1"}
            self.method = "POST"

    request = DummyRequest()
    proxy = openai_router._JsonRequestProxy(request, {"ok": True})

    assert proxy.state is request.state
    assert proxy.headers == {"x-test": "1"}
    assert proxy.method == "POST"
    assert asyncio.run(proxy.json()) == {"ok": True}


def test_responses_api_routes_to_chat_completions_payload():
    upstream_response = JSONResponse(
        content={
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "model": "gpt-5.5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt5.5",
                "instructions": "be concise",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
                "max_output_tokens": 20,
                "stop": ["END"],
                "store": True,
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["model"] == "gpt-5.5"
    assert body["output_text"] == "ok"
    assert body["output"][0]["content"][0]["type"] == "output_text"
    assert body["usage"]["input_tokens"] == 3
    assert body["usage"]["output_tokens"] == 2
    assert body["usage"]["total_tokens"] == 5
    assert body["store"] is True
    assert body["max_output_tokens"] == 20
    assert body["instructions"] == "be concise"

    routed_request = send_request.await_args.args[0]
    assert routed_request.model == "gpt-5.5"
    assert routed_request.messages[0].role == "system"
    assert routed_request.messages[0].content == "be concise"
    assert routed_request.messages[1].role == "user"
    assert routed_request.messages[1].content == "hello"
    assert routed_request.max_tokens is None
    assert routed_request.max_completion_tokens == 20
    assert routed_request.stop == ["END"]


def test_responses_api_converts_tools_structured_output_and_file_inputs():
    upstream_response = JSONResponse(
        content={
            "id": "chatcmpl_test",
            "object": "chat.completion",
            "model": "gpt-5.5",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt5.5",
                "input": [
                    {"role": "developer", "content": "follow the schema"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "inspect this"},
                            {"type": "input_image", "image_url": "https://example.test/a.png", "detail": "low"},
                            {"type": "input_file", "filename": "a.txt", "file_data": "hello file"},
                        ],
                    },
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "look up data",
                        "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                        "strict": True,
                    }
                ],
                "tool_choice": {"type": "function", "name": "lookup"},
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "answer",
                        "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
                        "strict": True,
                    }
                },
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    routed_request = send_request.await_args.args[0]
    assert routed_request.messages[0].role == "system"
    assert routed_request.messages[0].content == "follow the schema"
    assert routed_request.messages[1].content == [
        {"type": "text", "text": "inspect this"},
        {"type": "image_url", "image_url": {"url": "https://example.test/a.png", "detail": "low"}},
        {"type": "text", "text": "File a.txt:\nhello file"},
    ]
    assert routed_request.tools == [
        {
            "type": "function",
            "function": {
                "name": "lookup",
                "description": "look up data",
                "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                "strict": True,
            },
        }
    ]
    assert routed_request.tool_choice == {"type": "function", "function": {"name": "lookup"}}
    assert routed_request.response_format == {
        "type": "json_schema",
        "json_schema": {
            "name": "answer",
            "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}},
            "strict": True,
        },
    }


def test_responses_api_converts_tool_call_history_to_chat_messages():
    upstream_response = JSONResponse(
        content={
            "id": "chatcmpl_history",
            "object": "chat.completion",
            "model": "gpt-5.5",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt5.5",
                "input": [
                    {
                        "type": "function_call",
                        "call_id": "call_1",
                        "name": "lookup",
                        "arguments": {"q": "x"},
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call_1",
                        "output": {"ok": True},
                    },
                    {"role": "user", "content": "continue"},
                ],
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    routed_request = send_request.await_args.args[0]
    assert routed_request.messages[0].role == "assistant"
    assert routed_request.messages[0].content == ""
    assert routed_request.messages[0].tool_calls == [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "lookup", "arguments": "{\"q\": \"x\"}"},
        }
    ]
    assert routed_request.messages[1].role == "tool"
    assert routed_request.messages[1].tool_call_id == "call_1"
    assert routed_request.messages[1].content == "{\"ok\": true}"
    assert routed_request.messages[2].role == "user"
    assert routed_request.messages[2].content == "continue"


def test_responses_api_rejects_unsupported_state_and_builtin_tools():
    client = TestClient(_build_app())

    state_response = client.post(
        "/v1/responses",
        json={
            "model": "gpt5.5",
            "previous_response_id": "resp_old",
            "input": "continue",
        },
        headers={"Authorization": "Bearer test"},
    )
    assert state_response.status_code == 400
    assert "previous_response_id" in state_response.json()["detail"]

    tool_response = client.post(
        "/v1/responses",
        json={
            "model": "gpt5.5",
            "input": "search",
            "tools": [{"type": "web_search_preview"}],
        },
        headers={"Authorization": "Bearer test"},
    )
    assert tool_response.status_code == 400
    assert "web_search_preview" in tool_response.json()["detail"]


def test_responses_api_converts_chat_tool_calls_to_response_output_items():
    upstream_response = JSONResponse(
        content={
            "id": "chatcmpl_tools",
            "object": "chat.completion",
            "model": "gpt-5.5",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "lookup", "arguments": "{\"q\":\"x\"}"},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/responses",
            json={"model": "gpt5.5", "input": "lookup"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    output = response.json()["output"]
    assert output[0]["type"] == "function_call"
    assert output[0]["call_id"] == "call_1"
    assert output[0]["name"] == "lookup"
    assert json.loads(output[0]["arguments"]) == {"q": "x"}


def test_responses_api_preserves_usage_detail_fields():
    upstream_response = JSONResponse(
        content={
            "id": "chatcmpl_usage",
            "object": "chat.completion",
            "model": "gpt-5.5",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 4,
                "prompt_tokens_details": {"cached_tokens": 2},
                "completion_tokens": 6,
                "completion_tokens_details": {"reasoning_tokens": 3},
                "total_tokens": 10,
            },
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/responses",
            json={"model": "gpt5.5", "input": "hello"},
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    usage = response.json()["usage"]
    assert usage["input_tokens"] == 4
    assert usage["input_tokens_details"]["cached_tokens"] == 2
    assert usage["output_tokens"] == 6
    assert usage["output_tokens_details"] == {"reasoning_tokens": 3}
    assert usage["total_tokens"] == 10


def test_responses_api_stream_converts_chat_chunks_to_response_events():
    async def fake_stream(request_data, trace=None):
        async def iterator():
            yield b'data: {"choices":[{"delta":{"content":"he"},"finish_reason":null}]}\n\n'
            yield b'data: {"choices":[{"delta":{"content":"llo"},"finish_reason":null}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(iterator(), media_type="text/event-stream")

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.fake_stream_response_for_assembly", new=fake_stream):
        client = TestClient(_build_app())
        with client.stream(
            "POST",
            "/v1/responses",
            json={"model": "假流式/gpt5.5", "input": "hello", "stream": True},
            headers={"Authorization": "Bearer test"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: response.output_text.delta" in body
    assert '"delta":"he"' in body
    assert '"delta":"llo"' in body
    assert "event: response.completed" in body
    assert '"output_text":"hello"' in body
    assert "data: [DONE]" in body


def test_responses_api_stream_converts_tool_call_chunks_to_response_events():
    async def fake_stream(request_data, trace=None):
        async def iterator():
            yield b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"lookup","arguments":"{\\"q\\""}}]}}]}\n\n'
            yield b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":":\\"x\\"}"}}]}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return StreamingResponse(iterator(), media_type="text/event-stream")

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.fake_stream_response_for_assembly", new=fake_stream):
        client = TestClient(_build_app())
        with client.stream(
            "POST",
            "/v1/responses",
            json={"model": "假流式/gpt5.5", "input": "lookup", "stream": True},
            headers={"Authorization": "Bearer test"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: response.output_item.added" in body
    assert "event: response.function_call_arguments.delta" in body
    assert "event: response.function_call_arguments.done" in body
    assert '"name":"lookup"' in body
    assert '"arguments":"{\\"q\\":\\"x\\"}"' in body
