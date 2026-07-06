from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

import config
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


def test_normalize_model_id_accepts_gpt55_without_dash():
    assert config.normalize_model_id("gpt5.5") == "gpt-5.5"
    assert config.normalize_model_id("GPT 5.5") == "gpt-5.5"
    assert config.normalize_model_id("gpt-5.5") == "gpt-5.5"


def test_gpt55_alias_is_treated_as_native_streaming_model():
    assert config.supports_real_streaming_model("gpt5.5") is True


def test_chat_completions_normalizes_gpt55_before_upstream_send():
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt5.5",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    routed_request = send_request.await_args.args[0]
    assert routed_request.model == "gpt-5.5"


def test_chat_completions_normalizes_string_fallback_aliases():
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt5.5",
                "messages": [{"role": "user", "content": "hello"}],
                "fallbacks": ["gpt5.5", "gpt-5"],
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    routed_request = send_request.await_args.args[0]
    assert routed_request.fallbacks == ["gpt-5.5", "gpt-5"]


def test_v1_post_alias_routes_chat_completion_payload():
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )
    send_request = AsyncMock(return_value=upstream_response)

    with patch("src.api.openai_router.get_performance_tracker", new=AsyncMock(return_value=_Tracker())), \
         patch("src.api.openai_router.send_assembly_request", new=send_request):
        client = TestClient(_build_app())
        response = client.post(
            "/v1",
            json={
                "model": "gpt5.5",
                "messages": [{"role": "user", "content": "hello"}],
            },
            headers={"Authorization": "Bearer test"},
        )

    assert response.status_code == 200
    routed_request = send_request.await_args.args[0]
    assert routed_request.model == "gpt-5.5"
