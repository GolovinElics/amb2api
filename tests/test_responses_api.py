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
    assert body["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}

    routed_request = send_request.await_args.args[0]
    assert routed_request.model == "gpt-5.5"
    assert routed_request.messages[0].role == "system"
    assert routed_request.messages[0].content == "be concise"
    assert routed_request.messages[1].role == "user"
    assert routed_request.messages[1].content == [{"type": "text", "text": "hello"}]
    assert routed_request.max_tokens is None
    assert routed_request.max_completion_tokens == 20


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
