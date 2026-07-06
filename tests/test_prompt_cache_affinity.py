from unittest.mock import AsyncMock, patch

import pytest

from src.models.models import ChatCompletionRequest
from src.services import assembly_client
from src.services.assembly_client import (
    _apply_prompt_cache_defaults,
    _build_prompt_cache_affinity_key,
    _rank_indices_by_affinity,
)


def test_prompt_cache_defaults_adds_claude_system_cache_control_only():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "stable system instructions"},
            {"role": "user", "content": "dynamic question"},
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert out["messages"][0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert "cache_control" not in out["messages"][1]
    assert "cache_control" not in payload["messages"][0], "helper must not mutate caller payload"


def test_prompt_cache_defaults_preserves_explicit_cache_control():
    explicit = {"type": "ephemeral", "ttl": "1h"}
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "stable system instructions", "cache_control": explicit},
            {"role": "user", "content": "dynamic question"},
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert out["messages"][0]["cache_control"] == explicit


def test_prompt_cache_defaults_marks_claude_history_before_latest_user():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "user", "content": "stable prior question"},
            {"role": "assistant", "content": "stable prior answer"},
            {"role": "user", "content": "current dynamic question"},
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert out["messages"][1]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert "cache_control" not in out["messages"][2]
    assert "cache_control" not in payload["messages"][1], "helper must not mutate caller payload"


def test_prompt_cache_defaults_ignores_tools_for_single_dynamic_claude_turn():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "current dynamic question"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="1h",
    )

    assert "cache_control" not in out
    assert "cache_control" not in out["messages"][0]
    assert "cache_control" not in payload


def test_prompt_cache_defaults_ignores_empty_tools_for_single_dynamic_claude_turn():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "current dynamic question"}],
        "tools": [],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert "cache_control" not in out
    assert "cache_control" not in out["messages"][0]


def test_prompt_cache_defaults_ignores_default_text_response_format_for_claude_turn():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "current dynamic question"}],
        "response_format": {"type": "text"},
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert "cache_control" not in out
    assert "cache_control" not in out["messages"][0]


def test_prompt_cache_defaults_ignores_structured_output_for_single_dynamic_claude_turn():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "current dynamic question"}],
        "response_format": {"type": "json_object"},
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="1h",
    )

    assert "cache_control" not in out
    assert "cache_control" not in out["messages"][0]


def test_prompt_cache_defaults_leaves_single_dynamic_claude_turn_unmarked():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [{"role": "user", "content": "current dynamic question"}],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert "cache_control" not in out
    assert "cache_control" not in out["messages"][0]


def test_prompt_cache_defaults_does_not_generate_openai_key_for_empty_tools_only():
    payload = {
        "model": "gpt-4.1",
        "messages": [{"role": "user", "content": "current dynamic question"}],
        "tools": [],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="gpt-4.1",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert "prompt_cache_key" not in out


def test_prompt_cache_defaults_generates_safe_openai_cache_key_from_stable_prefix():
    payload = {
        "model": "gpt-4.1",
        "messages": [
            {"role": "system", "content": "stable system instructions that should not leak"},
            {"role": "user", "content": "dynamic question"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="gpt-4.1",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert out["prompt_cache_key"].startswith("amb2api:")
    assert "stable system instructions" not in out["prompt_cache_key"]
    assert "cache_control" not in out["messages"][0]


def test_prompt_cache_defaults_does_not_generate_key_for_kimi():
    payload = {
        "model": "kimi-k2.5",
        "messages": [
            {"role": "system", "content": "stable system instructions"},
            {"role": "user", "content": "dynamic question"},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}},
                },
            }
        ],
    }

    out = _apply_prompt_cache_defaults(
        payload,
        model="kimi-k2.5",
        auto_mode="conservative",
        default_ttl="5m",
    )

    assert "prompt_cache_key" not in out


def test_prompt_cache_metadata_records_auto_defaults_without_sensitive_values():
    payload = {
        "model": "claude-sonnet-4-6",
        "messages": [
            {"role": "system", "content": "stable system instructions that should not leak"},
            {"role": "user", "content": "dynamic question"},
        ],
    }
    out = _apply_prompt_cache_defaults(
        payload,
        model="claude-sonnet-4-6",
        auto_mode="conservative",
        default_ttl="1h",
    )

    metadata = assembly_client._build_prompt_cache_metadata(
        payload,
        out,
        model="claude-sonnet-4-6",
        enabled=True,
        auto_mode="conservative",
        default_ttl="1h",
        affinity_enabled=True,
        affinity_key="prompt_cache_auto:abcdef",
    )

    assert metadata["prompt_cache_enabled"] is True
    assert metadata["prompt_cache_auto_mode"] == "conservative"
    assert metadata["prompt_cache_default_ttl"] == "1h"
    assert metadata["prompt_cache_control_before"] is False
    assert metadata["prompt_cache_control_after"] is True
    assert metadata["prompt_cache_auto_applied_cache_control"] is True
    assert metadata["prompt_cache_key_before"] is False
    assert metadata["prompt_cache_key_after"] is False
    assert metadata["prompt_cache_auto_applied_key"] is False
    assert metadata["prompt_cache_affinity_enabled"] is True
    assert metadata["prompt_cache_affinity_key_used"] is True
    assert "stable system instructions" not in repr(metadata)


def test_prompt_cache_metadata_tolerates_missing_or_null_messages():
    for before_payload, after_payload in (
        ({}, {}),
        ({"messages": None}, {"messages": None}),
        ({"messages": {"role": "user", "content": "not a list"}}, {}),
    ):
        metadata = assembly_client._build_prompt_cache_metadata(
            before_payload,
            after_payload,
            model="claude-sonnet-4-6",
            enabled=True,
            auto_mode="conservative",
            default_ttl="5m",
            affinity_enabled=False,
            affinity_key=None,
        )

        assert metadata["prompt_cache_control_before"] is False
        assert metadata["prompt_cache_control_after"] is False


def test_prompt_cache_affinity_key_prefers_explicit_prompt_cache_key():
    payload = {
        "model": "gpt-4.1",
        "prompt_cache_key": "support-agent-v1",
        "messages": [{"role": "system", "content": "stable"}],
    }

    affinity_key = _build_prompt_cache_affinity_key(payload, "gpt-4.1")

    assert affinity_key == "prompt_cache_key:gpt-4.1:support-agent-v1"


def test_rank_indices_by_affinity_is_stable_per_key():
    indices = [0, 1, 2, 3]

    first = _rank_indices_by_affinity(indices, "stage-a")
    second = _rank_indices_by_affinity(indices, "stage-a")

    assert first == second
    assert sorted(first) == indices


class _FakeResponse:
    status_code = 200
    headers = {}
    text = (
        '{"id":"resp_1","model":"kimi-k2.5",'
        '"choices":[{"index":0,"message":{"role":"assistant","content":"ok"},"finish_reason":"stop"}],'
        '"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}'
    )

    def json(self):
        import json

        return json.loads(self.text)


class _FakeClientCtx:
    def __init__(self, capture):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, endpoint, content=None, headers=None):
        import json

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


def _patch_send_assembly_for_prompt_cache(monkeypatch, capture, *, prompt_cache_enabled=False):
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
        AsyncMock(return_value=prompt_cache_enabled),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_prompt_cache_auto_mode",
        AsyncMock(return_value="conservative"),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_prompt_cache_default_ttl",
        AsyncMock(return_value="5m"),
    )
    monkeypatch.setattr(
        "src.services.assembly_client.get_prompt_cache_affinity_enabled",
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
async def test_kimi_request_drops_explicit_prompt_cache_key_before_upstream_post(monkeypatch):
    capture = {}
    _patch_send_assembly_for_prompt_cache(monkeypatch, capture, prompt_cache_enabled=False)

    req = ChatCompletionRequest(
        model="kimi-k2.5",
        messages=[{"role": "user", "content": "hi"}],
        prompt_cache_key="user-provided-key",
    )

    await assembly_client.send_assembly_request(req, is_streaming=False)

    assert "prompt_cache_key" not in capture["payload"]


@pytest.mark.asyncio
async def test_select_key_with_daily_quota_uses_affinity_order():
    keys = ["sk-a", "sk-b", "sk-c"]

    class _FakeUnified:
        async def reserve_key_for_model(self, api_key, model):
            return {"allowed": True}

    with patch("src.stats.unified_stats.get_unified_stats", new=AsyncMock(return_value=_FakeUnified())):
        with patch(
            "src.services.assembly_client._get_affinity_candidate_indices",
            new=AsyncMock(return_value=[2, 0, 1]),
        ):
            first = await assembly_client._select_key_with_daily_quota(
                keys,
                "gpt-4.1",
                affinity_key="stage-a",
            )
            second = await assembly_client._select_key_with_daily_quota(
                keys,
                "gpt-4.1",
                affinity_key="stage-a",
            )

    assert first["idx"] == 2
    assert first["api_key"] == "sk-c"
    assert second["idx"] == 2
    assert second["api_key"] == "sk-c"


@pytest.mark.asyncio
async def test_select_key_with_daily_quota_affinity_skips_quota_blocked_candidate():
    keys = ["sk-a", "sk-b", "sk-c"]

    class _FakeUnified:
        async def reserve_key_for_model(self, api_key, model):
            if api_key == "sk-c":
                return {
                    "allowed": False,
                    "reason": "model_limit_reached",
                    "model": model,
                    "success_count": 10,
                    "total_limit": 100,
                    "model_success_count": 10,
                    "model_limit": 10,
                    "next_reset_time": "2099-01-01T07:00:00+00:00",
                }
            return {"allowed": True}

    with patch("src.stats.unified_stats.get_unified_stats", new=AsyncMock(return_value=_FakeUnified())):
        with patch(
            "src.services.assembly_client._get_affinity_candidate_indices",
            new=AsyncMock(return_value=[2, 1, 0]),
        ):
            selected = await assembly_client._select_key_with_daily_quota(
                keys,
                "gpt-4.1",
                affinity_key="stage-a",
            )

    assert selected["idx"] == 1
    assert selected["api_key"] == "sk-b"


@pytest.mark.asyncio
async def test_select_key_with_daily_quota_affinity_miss_falls_back_to_normal_selector():
    keys = ["sk-a", "sk-b"]

    class _FakeUnified:
        async def reserve_key_for_model(self, api_key, model):
            return {"allowed": True}

    with patch("src.stats.unified_stats.get_unified_stats", new=AsyncMock(return_value=_FakeUnified())):
        with patch(
            "src.services.assembly_client._get_affinity_candidate_indices",
            new=AsyncMock(return_value=[]),
        ):
            with patch(
                "src.services.assembly_client._next_key_index_async",
                new=AsyncMock(return_value=1),
            ) as fallback_selector:
                selected = await assembly_client._select_key_with_daily_quota(
                    keys,
                    "gpt-4.1",
                    affinity_key="stage-a",
                )

    assert selected["idx"] == 1
    assert selected["api_key"] == "sk-b"
    fallback_selector.assert_awaited()


@pytest.mark.asyncio
async def test_select_key_with_daily_quota_affinity_quota_blocks_fall_back_to_normal_selector():
    keys = ["sk-a", "sk-b", "sk-c"]

    class _FakeUnified:
        async def reserve_key_for_model(self, api_key, model):
            if api_key in ("sk-a", "sk-b"):
                return {
                    "allowed": False,
                    "reason": "model_limit_reached",
                    "model": model,
                    "success_count": 10,
                    "total_limit": 100,
                    "model_success_count": 10,
                    "model_limit": 10,
                    "next_reset_time": "2099-01-01T07:00:00+00:00",
                }
            return {"allowed": True}

    with patch("src.stats.unified_stats.get_unified_stats", new=AsyncMock(return_value=_FakeUnified())):
        with patch(
            "src.services.assembly_client._get_affinity_candidate_indices",
            new=AsyncMock(return_value=[0, 1]),
        ):
            with patch(
                "src.services.assembly_client._next_key_index_async",
                new=AsyncMock(return_value=2),
            ) as fallback_selector:
                selected = await assembly_client._select_key_with_daily_quota(
                    keys,
                    "gpt-4.1",
                    affinity_key="stage-a",
                )

    assert selected["idx"] == 2
    assert selected["api_key"] == "sk-c"
    fallback_selector.assert_awaited()
