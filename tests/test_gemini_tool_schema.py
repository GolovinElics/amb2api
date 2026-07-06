import json
from unittest.mock import AsyncMock

import pytest

from src.models.models import ChatCompletionRequest
from src.services.assembly_client import send_assembly_request


class _FakeResponse:
    status_code = 200
    headers = {}
    text = (
        '{"id":"resp_1","model":"gemini-3.5-flash",'
        '"choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}'
    )

    def json(self):
        return json.loads(self.text)


class _FakeClientCtx:
    def __init__(self, capture):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, endpoint, content=None, headers=None):
        self._capture["endpoint"] = endpoint
        self._capture["headers"] = headers
        self._capture["payload"] = json.loads(content)
        return _FakeResponse()


class _FakeHttpClient:
    def __init__(self, capture):
        self._capture = capture

    def get_client(self, timeout=None):
        return _FakeClientCtx(self._capture)


class _FakeUnifiedStats:
    async def record_call(self, *args, **kwargs):
        return None

    def release_reservation(self, *args, **kwargs):
        return None


def _patch_send_assembly(monkeypatch, capture):
    monkeypatch.setattr(
        "src.services.assembly_client.get_model_region",
        AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_assembly_endpoint",
        AsyncMock(return_value="https://example.test/v1/chat/completions"),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_assembly_api_keys",
        AsyncMock(return_value=["key-1"]),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_tool_debug_logs_enabled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_retry_429_max_retries",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_retry_429_enabled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_retry_429_interval",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_prompt_cache_enabled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_auto_ban_enabled",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "src.services.assembly_client._select_key_with_daily_quota",
        AsyncMock(return_value={"idx": 0, "api_key": "key-1", "reason": "", "blocked": []}),
    )
    monkeypatch.setattr(
        "src.services.assembly_client._update_rate_limit_info",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("src.services.assembly_client.http_client", _FakeHttpClient(capture))
    monkeypatch.setattr(
        "src.stats.unified_stats.get_unified_stats",
        AsyncMock(return_value=_FakeUnifiedStats()),
    )


@pytest.mark.asyncio
async def test_gemini_request_sanitizes_openai_tool_schema_before_upstream_post(monkeypatch):
    capture = {}
    _patch_send_assembly(monkeypatch, capture)

    req = ChatCompletionRequest(
        model="gemini-3.5-flash",
        messages=[{"role": "user", "content": "run task"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "Task",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "description": {"type": ["string", "null"]},
                            "mode": {"const": "fast", "type": "string"},
                            "steps": {
                                "type": "array",
                                "items": {
                                    "type": ["object", "null"],
                                    "properties": {"id": {"type": ["integer", "string"]}},
                                },
                            },
                        },
                    },
                },
            }
        ],
    )

    response = await send_assembly_request(req, is_streaming=False)

    assert response.status_code == 200
    params = capture["payload"]["tools"][0]["function"]["parameters"]
    assert params["properties"]["description"] == {"type": "string", "nullable": True}
    assert params["properties"]["mode"] == {"type": "string", "enum": ["fast"]}
    assert params["properties"]["steps"]["items"]["type"] == "object"
    assert params["properties"]["steps"]["items"]["nullable"] is True
    assert params["properties"]["steps"]["items"]["properties"]["id"]["type"] == "integer"
