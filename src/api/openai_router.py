"""
OpenAI Router - Handles OpenAI format API requests
处理OpenAI格式请求的路由模块
"""
import json
import time
import uuid
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from config import (
    get_available_models_async,
    get_base_model_from_feature_model,
    is_fake_streaming_model,
    normalize_model_id,
)
from log import log
from ..services.assembly_client import send_assembly_request
from ..services.assembly_stream_handler import fake_stream_response_for_assembly, convert_streaming_response
from ..models.models import ChatCompletionRequest, ModelList, Model
from ..transform.openai_transfer import assembly_response_to_openai
from ..transform.claude_to_openai import convert_claude_request_to_openai
from ..transform.openai_to_claude import (
    openai_response_to_anthropic,
    convert_openai_sse_to_anthropic_events,
    anthropic_events_to_sse_bytes,
    openai_error_to_anthropic_error,
    estimate_input_tokens,
    openai_models_to_anthropic,
)
from ..stats.performance_tracker import annotate_cache_usage_metadata, get_performance_tracker



# 创建路由器
router = APIRouter()
security = HTTPBearer()

# AssemblyAI 适配不需要 Google 凭证管理器


def _openai_v1_discovery_payload() -> Dict[str, Any]:
    return {
        "object": "amb2api.endpoint",
        "message": "amb2api OpenAI-compatible API",
        "endpoints": {
            "models": "/v1/models",
            "chat_completions": "/v1/chat/completions",
            "responses": "/v1/responses",
            "anthropic_messages": "/v1/messages",
        },
    }


def _normalize_request_model_ids(request_data: ChatCompletionRequest) -> None:
    original_model = str(getattr(request_data, "model", "") or "")
    normalized_model = normalize_model_id(original_model)
    if normalized_model and normalized_model != original_model:
        log.info(f"Normalized model id: {original_model} -> {normalized_model}")
        request_data.model = normalized_model

    fallbacks = getattr(request_data, "fallbacks", None)
    if not isinstance(fallbacks, list):
        return

    normalized_fallbacks: List[Any] = []
    changed = False
    for fallback in fallbacks:
        if isinstance(fallback, str):
            normalized_fallback = normalize_model_id(fallback)
            normalized_fallbacks.append(normalized_fallback)
            if normalized_fallback != fallback:
                changed = True
            continue
        if not isinstance(fallback, dict):
            normalized_fallbacks.append(fallback)
            continue
        normalized_fallback = dict(fallback)
        for key in ("model", "name"):
            value = normalized_fallback.get(key)
            if isinstance(value, str) and value.strip():
                normalized_value = normalize_model_id(value)
                if normalized_value != value:
                    normalized_fallback[key] = normalized_value
                    changed = True
        normalized_fallbacks.append(normalized_fallback)

    if changed:
        setattr(request_data, "fallbacks", normalized_fallbacks)


class _JsonRequestProxy:
    """Small request shim used when compatibility routes reuse chat_completions."""

    def __init__(self, request: Request, payload: Dict[str, Any]):
        self._request = request
        self.state = request.state
        self._payload = payload

    def __getattr__(self, name: str) -> Any:
        return getattr(self._request, name)

    async def json(self) -> Dict[str, Any]:
        return self._payload


class _ResponsesCompatibilityError(ValueError):
    """Raised when a Responses API feature cannot be represented safely."""


_RESPONSES_UNSUPPORTED_STATE_KEYS = {
    "background",
    "conversation",
    "context_management",
    "previous_response_id",
}
_RESPONSES_BUILTIN_TOOL_TYPES = {
    "code_interpreter",
    "computer_use_preview",
    "file_search",
    "image_generation",
    "mcp",
    "web_search",
    "web_search_preview",
}
_RESPONSES_TRUNCATION_FINISH_REASONS = {"length", "max_tokens"}


def _responses_role_to_chat(role: Any) -> str:
    role_text = str(role or "user")
    if role_text == "developer":
        return "system"
    return role_text


def _responses_content_part_to_chat(part: Any) -> Any:
    if not isinstance(part, dict):
        return part

    part_type = part.get("type")
    if part_type in {"input_text", "output_text"}:
        return {"type": "text", "text": str(part.get("text") or "")}
    if part_type == "input_image":
        image_url = part.get("image_url") or part.get("file_url")
        if image_url:
            image_part = {"type": "image_url", "image_url": {"url": image_url}}
            if isinstance(part.get("detail"), str):
                image_part["image_url"]["detail"] = part["detail"]
            return image_part
        raise _ResponsesCompatibilityError("input_image with file_id is not supported")
    if part_type == "input_file":
        if isinstance(part.get("file_data"), str):
            filename = part.get("filename") or "file"
            return {"type": "text", "text": f"File {filename}:\n{part['file_data']}"}
        if isinstance(part.get("file_url"), str):
            filename = part.get("filename") or "file"
            return {"type": "text", "text": f"File {filename}: {part['file_url']}"}
        raise _ResponsesCompatibilityError("input_file requires file_data or file_url")
    if part_type == "refusal":
        return {"type": "text", "text": str(part.get("refusal") or "")}
    if part_type is None:
        return part
    raise _ResponsesCompatibilityError(f"Unsupported Responses content type: {part_type}")


def _responses_output_message_to_chat(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = item.get("content")
    if isinstance(content, list):
        converted_parts = [_responses_content_part_to_chat(part) for part in content]
        text_parts = []
        rich_parts = []
        for part in converted_parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(str(part.get("text") or ""))
            else:
                rich_parts.append(part)
        if rich_parts:
            return {"role": _responses_role_to_chat(item.get("role") or "assistant"), "content": converted_parts}
        return {"role": _responses_role_to_chat(item.get("role") or "assistant"), "content": "".join(text_parts)}
    if isinstance(content, str):
        return {"role": _responses_role_to_chat(item.get("role") or "assistant"), "content": content}
    return None


def _responses_function_call_to_chat(item: Dict[str, Any]) -> Dict[str, Any]:
    arguments = item.get("arguments")
    if arguments is None:
        arguments = "{}"
    elif not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)

    call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:24]}")
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": str(item.get("name") or "unknown_function"),
                    "arguments": arguments,
                },
            }
        ],
    }


def _responses_function_call_output_to_chat(item: Dict[str, Any]) -> Dict[str, Any]:
    output = item.get("output")
    if output is None:
        output = ""
    elif not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False)
    return {
        "role": "tool",
        "tool_call_id": str(item.get("call_id") or item.get("id") or ""),
        "content": output,
    }


def _responses_input_to_chat_messages(raw_input: Any, instructions: Any = None) -> List[Dict[str, Any]]:
    messages: List[Dict[str, Any]] = []
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    input_items = raw_input if isinstance(raw_input, list) else [raw_input]
    for item in input_items:
        if isinstance(item, str):
            if item.strip():
                messages.append({"role": "user", "content": item})
            continue

        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type == "reasoning":
            continue
        if item_type in {"input_text", "output_text"}:
            text = str(item.get("text") or "")
            if text.strip():
                messages.append({"role": "user", "content": text})
            continue
        if item_type in {"input_image", "input_file"}:
            messages.append({"role": "user", "content": [_responses_content_part_to_chat(item)]})
            continue
        if item_type == "message" or "role" in item:
            message = _responses_output_message_to_chat(item)
            if message is not None:
                messages.append(message)
            continue
        if item_type == "function_call":
            messages.append(_responses_function_call_to_chat(item))
            continue
        if item_type == "function_call_output":
            messages.append(_responses_function_call_output_to_chat(item))
            continue

        role = item.get("role") or "user"
        content = item.get("content")
        if isinstance(content, list):
            content = [_responses_content_part_to_chat(part) for part in content]
        elif isinstance(content, dict):
            content = [_responses_content_part_to_chat(content)]
        elif content is None and isinstance(item.get("text"), str):
            content = item.get("text")

        if content is None:
            continue
        messages.append({"role": str(role), "content": content})

    return messages


def _responses_tools_to_chat_tools(tools: Any) -> Any:
    if tools is None:
        return None
    if not isinstance(tools, list):
        raise _ResponsesCompatibilityError("tools must be an array")

    chat_tools: List[Dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict):
            raise _ResponsesCompatibilityError("tool entries must be objects")
        tool_type = tool.get("type")
        if tool_type in _RESPONSES_BUILTIN_TOOL_TYPES:
            raise _ResponsesCompatibilityError(f"Responses built-in tool is not supported: {tool_type}")
        if tool_type != "function":
            raise _ResponsesCompatibilityError(f"Unsupported Responses tool type: {tool_type}")
        if isinstance(tool.get("function"), dict):
            chat_tools.append(tool)
            continue

        function: Dict[str, Any] = {"name": tool.get("name")}
        for key in ("description", "parameters", "strict"):
            if key in tool:
                function[key] = tool[key]
        if not function.get("name"):
            raise _ResponsesCompatibilityError("function tool name is required")
        chat_tools.append({"type": "function", "function": function})
    return chat_tools


def _responses_tool_choice_to_chat_tool_choice(tool_choice: Any) -> Any:
    if tool_choice is None or isinstance(tool_choice, str):
        return tool_choice
    if not isinstance(tool_choice, dict):
        raise _ResponsesCompatibilityError("tool_choice must be a string or object")

    choice_type = tool_choice.get("type")
    if choice_type == "function":
        name = tool_choice.get("name")
        if not name and isinstance(tool_choice.get("function"), dict):
            name = tool_choice["function"].get("name")
        if not name:
            raise _ResponsesCompatibilityError("function tool_choice name is required")
        return {"type": "function", "function": {"name": name}}
    if choice_type in _RESPONSES_BUILTIN_TOOL_TYPES:
        raise _ResponsesCompatibilityError(f"Responses built-in tool_choice is not supported: {choice_type}")
    return tool_choice


def _responses_text_format_to_chat_response_format(text_config: Any, raw_data: Dict[str, Any]) -> Any:
    if isinstance(text_config, dict) and isinstance(text_config.get("format"), dict):
        text_format = dict(text_config["format"])
        format_type = text_format.get("type")
        if format_type == "text":
            return None
        if format_type == "json_schema" and "json_schema" not in text_format:
            json_schema: Dict[str, Any] = {
                "name": text_format.get("name") or "response",
                "schema": text_format.get("schema") or {},
            }
            if "description" in text_format:
                json_schema["description"] = text_format["description"]
            if "strict" in text_format:
                json_schema["strict"] = text_format["strict"]
            return {"type": "json_schema", "json_schema": json_schema}
        return text_format
    return raw_data.get("response_format")


def _responses_request_to_chat_payload(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    unsupported = [
        key for key in _RESPONSES_UNSUPPORTED_STATE_KEYS
        if key in raw_data and raw_data.get(key) not in (None, False)
    ]
    if unsupported:
        raise _ResponsesCompatibilityError(
            "Unsupported Responses API state/background parameter(s): " + ", ".join(sorted(unsupported))
        )
    if raw_data.get("include"):
        raise _ResponsesCompatibilityError("Responses API include is not supported by this gateway")

    if "messages" in raw_data:
        messages = raw_data["messages"]
    else:
        messages = _responses_input_to_chat_messages(
            raw_data.get("input"),
            instructions=raw_data.get("instructions"),
        )

    payload: Dict[str, Any] = {
        "model": raw_data.get("model"),
        "messages": messages,
        "stream": bool(raw_data.get("stream", False)),
    }

    field_map = {
        "temperature": "temperature",
        "top_p": "top_p",
        "stop": "stop",
        "parallel_tool_calls": "parallel_tool_calls",
        "reasoning": "reasoning",
        "reasoning_effort": "reasoning_effort",
        "verbosity": "verbosity",
        "prompt_cache_key": "prompt_cache_key",
        "prompt_cache_retention": "prompt_cache_retention",
        "cache_control": "cache_control",
        "fallbacks": "fallbacks",
        "fallback_config": "fallback_config",
        "model_region": "model_region",
        "metadata": "metadata",
        "stream_options": "stream_options",
    }
    for source_key, target_key in field_map.items():
        if source_key in raw_data:
            payload[target_key] = raw_data[source_key]

    if "tools" in raw_data:
        payload["tools"] = _responses_tools_to_chat_tools(raw_data.get("tools"))
    if "tool_choice" in raw_data:
        payload["tool_choice"] = _responses_tool_choice_to_chat_tool_choice(raw_data.get("tool_choice"))

    if "max_output_tokens" in raw_data:
        payload["max_completion_tokens"] = raw_data["max_output_tokens"]
    elif "max_tokens" in raw_data:
        payload["max_tokens"] = raw_data["max_tokens"]

    response_format = _responses_text_format_to_chat_response_format(raw_data.get("text"), raw_data)
    if response_format is not None:
        payload["response_format"] = response_format

    return payload


def _json_response_to_payload(response: Any) -> Optional[Dict[str, Any]]:
    try:
        body = getattr(response, "body", None)
        if isinstance(body, bytes):
            return json.loads(body.decode("utf-8"))
        if isinstance(body, str):
            return json.loads(body)
    except Exception:
        return None
    return None


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    if content is None:
        return ""
    return str(content)


def _chat_tool_call_to_response_item(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
    arguments = function.get("arguments")
    if arguments is None and "input" in function:
        arguments = json.dumps(function.get("input") or {}, ensure_ascii=False)
    elif arguments is None:
        arguments = "{}"
    elif not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)

    call_id = str(tool_call.get("id") or f"call_{uuid.uuid4().hex[:24]}")
    return {
        "id": f"fc_{uuid.uuid4().hex}",
        "type": "function_call",
        "status": "completed",
        "call_id": call_id,
        "name": str(function.get("name") or "unknown_function"),
        "arguments": arguments,
    }


def _chat_message_to_response_output_items(message: Dict[str, Any]) -> tuple[List[Dict[str, Any]], str]:
    output_items: List[Dict[str, Any]] = []
    output_text = _message_content_to_text(message.get("content"))

    if output_text:
        output_items.append(
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": output_text,
                        "annotations": [],
                    }
                ],
            }
        )

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal:
        output_items.append(
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "refusal", "refusal": refusal}],
            }
        )

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                output_items.append(_chat_tool_call_to_response_item(tool_call))

    if not output_items:
        output_items.append(
            {
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "", "annotations": []}],
            }
        )

    return output_items, output_text


def _response_usage_token_count(usage: Dict[str, Any], primary_key: str, fallback_key: str) -> int:
    value = usage.get(primary_key, usage.get(fallback_key, 0))
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else 0
    except (TypeError, ValueError):
        return 0


def _chat_usage_to_response_usage(
    usage: Any,
    *,
    allow_empty: bool = False,
) -> Optional[Dict[str, Any]]:
    if not isinstance(usage, dict):
        return None
    usage_keys = {
        "prompt_tokens",
        "input_tokens",
        "completion_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens_details",
        "input_tokens_details",
        "completion_tokens_details",
        "output_tokens_details",
    }
    if not allow_empty and not any(key in usage for key in usage_keys):
        return None

    response_usage = {
        "input_tokens": _response_usage_token_count(usage, "prompt_tokens", "input_tokens"),
        "output_tokens": _response_usage_token_count(usage, "completion_tokens", "output_tokens"),
        "total_tokens": _response_usage_token_count(usage, "total_tokens", "total_tokens"),
    }
    if not response_usage["total_tokens"]:
        response_usage["total_tokens"] = response_usage["input_tokens"] + response_usage["output_tokens"]

    prompt_token_details = usage.get("prompt_tokens_details")
    if not isinstance(prompt_token_details, dict):
        prompt_token_details = usage.get("input_tokens_details")
    if isinstance(prompt_token_details, dict):
        response_usage["input_tokens_details"] = prompt_token_details

    completion_token_details = usage.get("completion_tokens_details")
    if not isinstance(completion_token_details, dict):
        completion_token_details = usage.get("output_tokens_details")
    if isinstance(completion_token_details, dict):
        response_usage["output_tokens_details"] = completion_token_details

    return response_usage


def _chat_completion_to_response_payload(
    chat_payload: Dict[str, Any],
    model: str,
    request_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    now = int(time.time())
    response_id = str(chat_payload.get("id") or f"resp_{uuid.uuid4().hex}")
    choices = chat_payload.get("choices") if isinstance(chat_payload.get("choices"), list) else []
    first_choice = choices[0] if choices and isinstance(choices[0], dict) else {}
    message = first_choice.get("message") if isinstance(first_choice.get("message"), dict) else {}
    output_items, output_text = _chat_message_to_response_output_items(message)
    finish_reason = first_choice.get("finish_reason")
    is_truncated = finish_reason in _RESPONSES_TRUNCATION_FINISH_REASONS
    status_value = "incomplete" if is_truncated else "completed"
    incomplete_details = {"reason": "max_output_tokens"} if is_truncated else None

    usage = chat_payload.get("usage") if isinstance(chat_payload.get("usage"), dict) else {}
    response_usage = _chat_usage_to_response_usage(usage, allow_empty=True) or {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }

    request_payload = request_payload or {}
    store = request_payload.get("store", False)
    if not isinstance(store, bool):
        store = False

    return {
        "id": response_id,
        "object": "response",
        "created_at": int(chat_payload.get("created") or now),
        "status": status_value,
        "model": chat_payload.get("model") or model,
        "output": output_items,
        "output_text": output_text,
        "usage": response_usage,
        "error": None,
        "incomplete_details": incomplete_details,
        "instructions": request_payload.get("instructions"),
        "max_output_tokens": request_payload.get("max_output_tokens"),
        "metadata": request_payload.get("metadata") or {},
        "parallel_tool_calls": request_payload.get("parallel_tool_calls"),
        "previous_response_id": None,
        "reasoning": request_payload.get("reasoning"),
        "store": store,
        "temperature": request_payload.get("temperature"),
        "text": request_payload.get("text"),
        "tool_choice": request_payload.get("tool_choice"),
        "tools": request_payload.get("tools") or [],
        "top_p": request_payload.get("top_p"),
        "truncation": request_payload.get("truncation", "disabled"),
        "user": request_payload.get("user"),
    }


def _responses_sse_event(event: str, payload: Dict[str, Any]) -> bytes:
    event_payload = dict(payload)
    event_payload.setdefault("type", event)
    event_payload.setdefault("event_id", f"event_{uuid.uuid4().hex}")
    return (
        f"event: {event}\n"
        f"data: {json.dumps(event_payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    ).encode("utf-8")


def _iter_sse_data_payloads(chunk: Any) -> List[str]:
    if isinstance(chunk, bytes):
        text = chunk.decode("utf-8", errors="replace")
    else:
        text = str(chunk)

    payloads: List[str] = []
    for event_block in text.split("\n\n"):
        for line in event_block.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                payloads.append(line[5:].strip())
    return payloads


def _chat_stream_chunk_delta(payload: Dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list):
        return ""

    parts: List[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta")
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                parts.append(content)
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def _chat_stream_to_responses_stream(chat_stream: StreamingResponse, model: str) -> StreamingResponse:
    async def responses_stream_generator():
        response_id = f"resp_{uuid.uuid4().hex}"
        text_item_id = f"msg_{uuid.uuid4().hex}"
        created_at = int(time.time())
        output_text_parts: List[str] = []
        output_items: List[Dict[str, Any]] = []
        text_output_index: Optional[int] = None
        next_output_index = 0
        function_calls: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None
        response_usage: Optional[Dict[str, Any]] = None

        response_payload = {
            "id": response_id,
            "object": "response",
            "created_at": created_at,
            "status": "in_progress",
            "model": model,
            "output": [],
            "error": None,
            "incomplete_details": None,
        }

        yield _responses_sse_event("response.created", {"response": response_payload})
        yield _responses_sse_event("response.in_progress", {"response": response_payload})

        async for chunk in chat_stream.body_iterator:
            for data_payload in _iter_sse_data_payloads(chunk):
                if not data_payload or data_payload == "[DONE]":
                    continue
                try:
                    chat_chunk = json.loads(data_payload)
                except Exception:
                    continue
                chunk_usage = _chat_usage_to_response_usage(chat_chunk.get("usage"))
                if chunk_usage is not None:
                    response_usage = chunk_usage
                delta = _chat_stream_chunk_delta(chat_chunk)
                if delta:
                    if text_output_index is None:
                        text_output_index = next_output_index
                        next_output_index += 1
                        yield _responses_sse_event(
                            "response.output_item.added",
                            {
                                "response_id": response_id,
                                "output_index": text_output_index,
                                "item": {
                                    "id": text_item_id,
                                    "type": "message",
                                    "status": "in_progress",
                                    "role": "assistant",
                                    "content": [],
                                },
                            },
                        )
                        yield _responses_sse_event(
                            "response.content_part.added",
                            {
                                "response_id": response_id,
                                "item_id": text_item_id,
                                "output_index": text_output_index,
                                "content_index": 0,
                                "part": {"type": "output_text", "text": "", "annotations": []},
                            },
                        )
                    output_text_parts.append(delta)
                    yield _responses_sse_event(
                        "response.output_text.delta",
                        {
                            "response_id": response_id,
                            "item_id": text_item_id,
                            "output_index": text_output_index,
                            "content_index": 0,
                            "delta": delta,
                        },
                    )

                for choice in chat_chunk.get("choices") or []:
                    if not isinstance(choice, dict):
                        continue
                    if isinstance(choice.get("finish_reason"), str) and choice.get("finish_reason"):
                        finish_reason = str(choice["finish_reason"])
                    choice_delta = choice.get("delta")
                    if not isinstance(choice_delta, dict):
                        choice_delta = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                    tool_calls = choice_delta.get("tool_calls")
                    if not isinstance(tool_calls, list):
                        continue
                    for tool_call in tool_calls:
                        if not isinstance(tool_call, dict):
                            continue
                        try:
                            tool_index = int(tool_call.get("index") or 0)
                        except (TypeError, ValueError):
                            tool_index = 0
                        function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                        entry = function_calls.get(tool_index)
                        if entry is None:
                            entry = {
                                "item_id": f"fc_{uuid.uuid4().hex}",
                                "call_id": str(tool_call.get("id") or f"call_{uuid.uuid4().hex[:24]}"),
                                "name": str(function.get("name") or ""),
                                "arguments_parts": [],
                                "output_index": next_output_index,
                            }
                            next_output_index += 1
                            function_calls[tool_index] = entry
                            yield _responses_sse_event(
                                "response.output_item.added",
                                {
                                    "response_id": response_id,
                                    "output_index": entry["output_index"],
                                    "item": {
                                        "id": entry["item_id"],
                                        "type": "function_call",
                                        "status": "in_progress",
                                        "call_id": entry["call_id"],
                                        "name": entry["name"],
                                        "arguments": "",
                                    },
                                },
                            )
                        if tool_call.get("id"):
                            entry["call_id"] = str(tool_call["id"])
                        if function.get("name"):
                            entry["name"] = str(function["name"])
                        arguments_delta = function.get("arguments")
                        if arguments_delta:
                            arguments_delta = str(arguments_delta)
                            entry["arguments_parts"].append(arguments_delta)
                            yield _responses_sse_event(
                                "response.function_call_arguments.delta",
                                {
                                    "response_id": response_id,
                                    "item_id": entry["item_id"],
                                    "output_index": entry["output_index"],
                                    "call_id": entry["call_id"],
                                    "delta": arguments_delta,
                                },
                            )

        output_text = "".join(output_text_parts)
        if text_output_index is not None:
            done_part = {"type": "output_text", "text": output_text, "annotations": []}
            done_item = {
                "id": text_item_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [done_part],
            }
            output_items.append(done_item)
            yield _responses_sse_event(
                "response.output_text.done",
                {
                    "response_id": response_id,
                    "item_id": text_item_id,
                    "output_index": text_output_index,
                    "content_index": 0,
                    "text": output_text,
                },
            )
            yield _responses_sse_event(
                "response.content_part.done",
                {
                    "response_id": response_id,
                    "item_id": text_item_id,
                    "output_index": text_output_index,
                    "content_index": 0,
                    "part": done_part,
                },
            )
            yield _responses_sse_event(
                "response.output_item.done",
                {"response_id": response_id, "output_index": text_output_index, "item": done_item},
            )

        for entry in sorted(function_calls.values(), key=lambda item: item["output_index"]):
            arguments = "".join(entry["arguments_parts"]) or "{}"
            done_item = {
                "id": entry["item_id"],
                "type": "function_call",
                "status": "completed",
                "call_id": entry["call_id"],
                "name": entry["name"] or "unknown_function",
                "arguments": arguments,
            }
            output_items.append(done_item)
            yield _responses_sse_event(
                "response.function_call_arguments.done",
                {
                    "response_id": response_id,
                    "item_id": entry["item_id"],
                    "output_index": entry["output_index"],
                    "call_id": entry["call_id"],
                    "name": done_item["name"],
                    "arguments": arguments,
                },
            )
            yield _responses_sse_event(
                "response.output_item.done",
                {"response_id": response_id, "output_index": entry["output_index"], "item": done_item},
            )

        if not output_items:
            output_items.append(
                {
                    "id": text_item_id,
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "", "annotations": []}],
                }
            )

        is_truncated = finish_reason in _RESPONSES_TRUNCATION_FINISH_REASONS
        final_status = "incomplete" if is_truncated else "completed"
        incomplete_details = {"reason": "max_output_tokens"} if is_truncated else None
        completed_response = dict(response_payload)
        completed_response["status"] = final_status
        completed_response["incomplete_details"] = incomplete_details
        completed_response["output"] = output_items
        completed_response["output_text"] = output_text
        if response_usage is not None:
            completed_response["usage"] = response_usage
        yield _responses_sse_event(
            "response.incomplete" if final_status == "incomplete" else "response.completed",
            {"response": completed_response},
        )
        yield b"data: [DONE]\n\n"

    return StreamingResponse(responses_stream_generator(), media_type="text/event-stream")


async def _should_use_fake_streaming(model: str, forced_by_model_prefix: bool) -> tuple[bool, str]:
    if forced_by_model_prefix:
        return True, "model-prefix"

    from config import get_enable_real_streaming, get_fake_streaming_enabled, supports_real_streaming_model

    if await get_fake_streaming_enabled():
        return True, "global-fake-streaming"
    if not await get_enable_real_streaming():
        return True, "legacy-real-streaming-disabled"
    if not supports_real_streaming_model(model):
        return True, "unsupported-native-streaming"
    return False, "native-streaming-supported"


def _annotate_stream_route_metadata(
    trace: Any,
    *,
    model: str,
    requested: bool,
    use_fake_route: bool,
    reason: str,
) -> None:
    if not trace:
        return
    try:
        from config import supports_real_streaming_model

        native_supported = supports_real_streaming_model(model)
    except Exception:
        native_supported = reason == "native-streaming-supported"

    trace.metadata["stream_requested"] = bool(requested)
    trace.metadata["stream_route_reason"] = str(reason or "")
    trace.metadata["native_stream_supported"] = bool(native_supported)
    trace.metadata["upstream_stream_requested"] = bool(requested and not use_fake_route)


def _is_retryable_stream_header_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code < 600


async def _request_native_stream_with_header_bootstrap_retries(
    request_provider,
    trace: Any = None,
):
    """Retry native stream setup when upstream fails before any SSE bytes."""
    response = await request_provider()
    response_status = getattr(response, "status_code", 200)
    if not _is_retryable_stream_header_status(response_status):
        return response, None

    try:
        from config import get_stream_bootstrap_retries

        retry_budget = max(0, int(await get_stream_bootstrap_retries()))
    except Exception:
        retry_budget = 0

    for attempt in range(1, retry_budget + 1):
        if trace:
            prior_bootstrap_retries = int(trace.metadata.get("stream_bootstrap_retries_used", 0) or 0)
            trace.metadata["stream_bootstrap_retries_used"] = prior_bootstrap_retries + 1
            trace.metadata["stream_header_bootstrap_retries_used"] = attempt
            trace.metadata["stream_header_bootstrap_last_status"] = response_status
        log.warning(
            f"[STREAM_HEADER_BOOTSTRAP_RETRY] attempt={attempt}/{retry_budget} "
            f"status={response_status}"
        )
        response = await request_provider()
        response_status = getattr(response, "status_code", 200)
        if not _is_retryable_stream_header_status(response_status):
            return response, max(0, retry_budget - attempt)

    return response, 0

async def _resolve_identity(request: Request, token: str) -> bool:
    """把 token 解析为身份并挂到 request.state.identity。

    接受两类凭证：① 主口令 API_PASSWORD（master，无限制）；② 有效的下游 user token
    （启用且未过期；配额/模型白名单在拿到 model 后于处理函数内强制）。
    返回是否通过鉴权。
    """
    from config import get_api_password
    from .auth import consteq
    password = await get_api_password()
    if token and consteq(token, password):  # 恒定时间比较，防计时攻击
        request.state.identity = {"master": True, "token": token, "meta": None}
        return True
    from ..services.token_manager import get_token_manager
    tm = await get_token_manager()
    # 鉴权只确立身份（存在/启用/未过期）；配额与模型白名单留给 enforce_token_quota，
    # 否则配额耗尽的 token 会在此被当成 403 密码错误，而非请求阶段的 429。
    v = await tm.validate(token, check_quota=False)
    if v.get("valid"):
        request.state.identity = {"master": False, "token": token, "meta": v["meta"]}
        return True
    return False


async def authenticate(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """验证主口令或下游 user token"""
    token = credentials.credentials
    if not await _resolve_identity(request, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    return token


def _extract_fallback_model_ids(fallbacks: Any) -> List[str]:
    """从 fallbacks 字段提取模型 id（兼容字符串数组或 {model/name: ...} 对象数组）。"""
    out: List[str] = []
    if isinstance(fallbacks, list):
        for fb in fallbacks:
            if isinstance(fb, str) and fb.strip():
                out.append(fb.strip())
            elif isinstance(fb, dict):
                m = fb.get("model") or fb.get("name")
                if isinstance(m, str) and m.strip():
                    out.append(m.strip())
    return out


async def enforce_token_quota(
    request: Request,
    model: str,
    consume: bool = True,
    fallback_models: Optional[List[str]] = None,
) -> None:
    """对 user token 强制：模型白名单 + 禁用/过期 + 配额。master 不受限。

    在处理函数拿到 model 后调用。配额耗尽 → 429；模型不允许/禁用/过期 → 403。
    consume=True 原子消费一次配额（计费端点）；consume=False 只校验访问权
    （白名单/禁用/过期），不消费、且不因配额耗尽而拒绝（用于 count_tokens 这类免费本地端点）。
    fallback_models 若提供，会与主模型受同一 allowed_models 白名单约束——否则受限 token 可
    借 fallbacks 绕过白名单请求未授权模型（主模型合法、回退模型非法，上游回退/重试时即被使用）。
    """
    identity = getattr(request.state, "identity", None)
    if not identity or identity.get("master"):
        return
    from ..services.token_manager import get_token_manager
    tm = await get_token_manager()
    # fallbacks 先于配额消费校验：避免非法回退请求白白扣掉一次配额。
    if fallback_models:
        meta = (await tm.validate(identity["token"], model, check_quota=False)).get("meta") or {}
        allowed = meta.get("allowed_models")
        if allowed is not None:
            for fb in fallback_models:
                if fb and fb not in allowed:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN, detail="model_not_allowed"
                    )
    if consume:
        res = await tm.try_consume(identity["token"], model)
    else:
        # 免费/本地端点：只校验身份+模型白名单，不消费、不因配额耗尽而拒绝
        res = await tm.validate(identity["token"], model, check_quota=False)
    if not res.get("valid"):
        reason = res.get("reason", "forbidden")
        if reason == "quota_exceeded":
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=reason)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

@router.get("/v1")
@router.get("/v1/")
async def openai_v1_root():
    """Lightweight discovery endpoint for clients that probe the OpenAI base URL."""
    return JSONResponse(content=_openai_v1_discovery_payload())


@router.get("/v1/models")
async def list_models(request: Request):
    """返回 OpenAI/Anthropic 兼容的模型列表。"""
    models = await get_available_models_async("openai")
    if request.headers.get("anthropic-version"):
        return JSONResponse(content=openai_models_to_anthropic([str(m) for m in models]))
    return ModelList(data=[Model(id=m) for m in models])


async def authenticate_anthropic_request(request: Request) -> str:
    """Anthropic-compatible auth: x-api-key first, then Bearer. 支持主口令或 user token。"""
    token = request.headers.get("x-api-key", "").strip()
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not await _resolve_identity(request, token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="密码错误")
    return token


def _extract_response_text(response: Any) -> str:
    """Decode generic response object to text."""
    if hasattr(response, "text") and isinstance(getattr(response, "text"), str):
        return response.text
    if hasattr(response, "body"):
        body = response.body
        if isinstance(body, bytes):
            return body.decode("utf-8", errors="replace")
        return str(body)
    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="replace")
        return str(content)
    return str(response)


def _parse_response_json(text: str, response: Any) -> Any:
    """Best-effort parse of response body as JSON."""
    parsed = None
    try:
        parsed = json.loads(text.strip())
    except Exception:
        if "data:" in text:
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            for line in reversed(lines):
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    continue
                try:
                    parsed = json.loads(payload)
                    break
                except Exception:
                    pass
        if parsed is None and hasattr(response, "json"):
            try:
                parsed = response.json()
            except Exception:
                parsed = None
    return parsed


async def _forward_openai_error_response(
    response: Any,
    response_status: int,
    trace: Any = None,
    tracker: Any = None,
) -> JSONResponse:
    """Return an upstream JSON/non-JSON error without wrapping it as a stream."""
    try:
        parsed_error = _parse_response_json(_extract_response_text(response), response)
    except Exception:
        parsed_error = None

    if trace and tracker:
        try:
            await tracker.end_trace(trace.trace_id, success=False)
        except Exception:
            pass

    if isinstance(parsed_error, dict):
        return JSONResponse(content=parsed_error, status_code=response_status)
    return JSONResponse(
        content={
            "error": {
                "message": f"Upstream request failed with status {response_status}",
                "type": "api_error",
            }
        },
        status_code=response_status,
    )


def _build_openai_fallback_text_response(model: str, text: str) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text.strip()},
                "finish_reason": "stop",
            }
        ],
    }


def _to_non_negative_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


def _extract_usage_metrics(usage: Any) -> Dict[str, int]:
    usage_map = usage if isinstance(usage, dict) else {}
    prompt_tokens = _to_non_negative_int(
        usage_map.get("prompt_tokens", usage_map.get("input_tokens", 0)),
        0,
    )
    completion_tokens = _to_non_negative_int(
        usage_map.get("completion_tokens", usage_map.get("output_tokens", 0)),
        0,
    )
    cached_tokens = _to_non_negative_int(
        usage_map.get("cached_tokens", usage_map.get("input_cached_tokens", 0)),
        0,
    )
    prompt_details = usage_map.get("prompt_tokens_details")
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    if cached_tokens == 0:
        cached_tokens = _to_non_negative_int(prompt_details.get("cached_tokens", 0), 0)

    cache_creation = prompt_details.get("cache_creation")
    if not isinstance(cache_creation, dict):
        cache_creation = {}
    cache_creation_5m = _to_non_negative_int(
        cache_creation.get("ephemeral_5m_input_tokens", 0), 0
    )
    cache_creation_1h = _to_non_negative_int(
        cache_creation.get("ephemeral_1h_input_tokens", 0), 0
    )

    total_tokens = _to_non_negative_int(
        usage_map.get("total_tokens", prompt_tokens + completion_tokens),
        prompt_tokens + completion_tokens,
    )
    total_tokens = max(total_tokens, prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_tokens": cached_tokens,
        "cache_creation_5m_tokens": cache_creation_5m,
        "cache_creation_1h_tokens": cache_creation_1h,
        "total_tokens": total_tokens,
    }


def _extract_openai_response_diagnostics(openai_response: Any) -> Dict[str, Any]:
    """Extract non-sensitive diagnostics from OpenAI-style response."""
    finish_reason = "-"
    tool_calls_count = 0

    if isinstance(openai_response, dict):
        choices = openai_response.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, dict):
                fr = first_choice.get("finish_reason")
                if fr is not None:
                    finish_reason = str(fr)
                message = first_choice.get("message")
                if isinstance(message, dict):
                    tool_calls = message.get("tool_calls")
                    if isinstance(tool_calls, list):
                        tool_calls_count = sum(1 for tc in tool_calls if isinstance(tc, dict))

    return {
        "finish_reason": finish_reason,
        "tool_calls_count": tool_calls_count,
    }


def _summarize_upstream_response_shape(response_data: Any) -> Dict[str, Any]:
    """Summarize non-sensitive upstream response shape for tool-call diagnostics."""
    summary: Dict[str, Any] = {
        "response_type": type(response_data).__name__,
        "choices_count": 0,
        "choice_shapes": [],
    }

    if not isinstance(response_data, dict):
        return summary

    choices = response_data.get("choices")
    if not isinstance(choices, list):
        return summary

    summary["choices_count"] = len(choices)
    choice_shapes = []
    for idx, choice in enumerate(choices[:3]):
        if not isinstance(choice, dict):
            choice_shapes.append({"index": idx, "choice_type": type(choice).__name__})
            continue

        msg = choice.get("message")
        msg_role = msg.get("role") if isinstance(msg, dict) else None
        msg_content = msg.get("content") if isinstance(msg, dict) else None
        msg_content_kind = type(msg_content).__name__
        content_block_types = []
        if isinstance(msg_content, list):
            for block in msg_content[:5]:
                if isinstance(block, dict):
                    block_type = block.get("type")
                    content_block_types.append(str(block_type) if block_type is not None else "-")
                else:
                    content_block_types.append(type(block).__name__)

        choice_tool_calls = choice.get("tool_calls")
        choice_tool_calls_count = (
            sum(1 for tc in choice_tool_calls if isinstance(tc, dict))
            if isinstance(choice_tool_calls, list)
            else 0
        )

        message_tool_calls = msg.get("tool_calls") if isinstance(msg, dict) else None
        message_tool_calls_count = (
            sum(1 for tc in message_tool_calls if isinstance(tc, dict))
            if isinstance(message_tool_calls, list)
            else 0
        )

        has_xml_function_calls = isinstance(msg_content, str) and "<function_calls>" in msg_content

        choice_shapes.append(
            {
                "index": idx,
                "finish_reason": choice.get("finish_reason"),
                "message_role": msg_role,
                "message_content_kind": msg_content_kind,
                "content_block_types": content_block_types,
                "choice_tool_calls_count": choice_tool_calls_count,
                "message_tool_calls_count": message_tool_calls_count,
                "has_xml_function_calls": has_xml_function_calls,
            }
        )

    summary["choice_shapes"] = choice_shapes
    return summary


def _update_stream_diagnostics_from_payload(payload_text: str, diag: Dict[str, Any]) -> None:
    """Update streaming diagnostics from one OpenAI SSE payload text."""
    payload = payload_text.strip()
    if not payload or payload == "[DONE]":
        return

    try:
        parsed = json.loads(payload)
    except Exception:
        return

    if not isinstance(parsed, dict):
        return

    choices = parsed.get("choices")
    if not isinstance(choices, list) or not choices:
        return

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return

    diag["chunk_count"] = int(diag.get("chunk_count", 0)) + 1

    delta = first_choice.get("delta")
    if isinstance(delta, dict):
        tool_calls = delta.get("tool_calls")
        if isinstance(tool_calls, list):
            diag["tool_calls_count"] = int(diag.get("tool_calls_count", 0)) + sum(
                1 for tc in tool_calls if isinstance(tc, dict)
            )

    finish_reason = first_choice.get("finish_reason")
    if finish_reason is not None:
        diag["finish_reason"] = str(finish_reason)


async def _convert_openai_stream_to_anthropic(
    openai_stream_response: StreamingResponse, model: str
) -> StreamingResponse:
    """Re-map OpenAI SSE stream body to Anthropic SSE events."""

    async def anthropic_stream_generator():
        state: Dict[str, Any] = {"model": model}
        stream_diag: Dict[str, Any] = {
            "chunk_count": 0,
            "tool_calls_count": 0,
            "finish_reason": "-",
        }
        buf = ""
        async for chunk in openai_stream_response.body_iterator:
            if isinstance(chunk, bytes):
                buf += chunk.decode("utf-8", errors="replace")
            else:
                buf += str(chunk)

            parts = buf.split("\n\n")
            buf = parts.pop()
            for part in parts:
                line = part.strip()
                if not line:
                    continue
                if line.startswith(":"):
                    yield f"{line}\n\n".encode("utf-8")
                    continue
                for single_line in line.splitlines():
                    single_line = single_line.strip()
                    if not single_line.startswith("data:"):
                        continue
                    payload = single_line[5:].strip()
                    _update_stream_diagnostics_from_payload(payload, stream_diag)
                    events = convert_openai_sse_to_anthropic_events(
                        payload, state=state, default_model=model
                    )
                    if events:
                        yield anthropic_events_to_sse_bytes(events)

        if buf.strip():
            line = buf.strip()
            if line.startswith("data:"):
                payload = line[5:].strip()
                _update_stream_diagnostics_from_payload(payload, stream_diag)
                events = convert_openai_sse_to_anthropic_events(
                    payload, state=state, default_model=model
                )
                if events:
                    yield anthropic_events_to_sse_bytes(events)

        # Ensure message_stop exists even if upstream only ended with [DONE].
        events = convert_openai_sse_to_anthropic_events(
            "[DONE]", state=state, default_model=model
        )
        if events:
            yield anthropic_events_to_sse_bytes(events)

        log.info(
            f"[ANTHROPIC_DIAG] stream=1 model={model} finish_reason={stream_diag.get('finish_reason', '-')} "
            f"tool_calls_count={stream_diag.get('tool_calls_count', 0)} chunk_count={stream_diag.get('chunk_count', 0)}"
        )

    return StreamingResponse(anthropic_stream_generator(), media_type="text/event-stream")


@router.post("/v1/messages")
async def anthropic_messages(
    request: Request,
):
    """处理 Anthropic Messages API 请求。"""
    try:
        await authenticate_anthropic_request(request)
    except HTTPException as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                e.status_code, {"message": str(e.detail)}, fallback_message=str(e.detail)
            ),
            status_code=e.status_code,
        )

    trace_id = str(uuid.uuid4())
    tracker = await get_performance_tracker()
    trace = tracker.start_trace(trace_id, "pending")
    trace.mark("auth_complete")

    try:
        raw_data = await request.json()
    except Exception as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                400, {"message": f"Invalid JSON: {str(e)}"}, fallback_message="Invalid JSON"
            ),
            status_code=400,
        )

    try:
        openai_payload = convert_claude_request_to_openai(raw_data)
    except Exception as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                400, {"message": str(e)}, fallback_message="Invalid request"
            ),
            status_code=400,
        )

    try:
        request_data = ChatCompletionRequest(**openai_payload)
        _normalize_request_model_ids(request_data)
        trace.model = request_data.model
    except Exception as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                400, {"message": f"Request validation error: {str(e)}"}, fallback_message="Request validation error"
            ),
            status_code=400,
        )

    # 多租户：对 user token 强制模型白名单 + 配额（包装成 Anthropic 错误壳）
    try:
        await enforce_token_quota(
            request,
            request_data.model,
            fallback_models=_extract_fallback_model_ids(getattr(request_data, "fallbacks", None)),
        )
    except HTTPException as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                e.status_code, {"message": str(e.detail)}, fallback_message=str(e.detail)
            ),
            status_code=e.status_code,
        )

    if getattr(request_data, "max_tokens", None) is not None and request_data.max_tokens > 65535:
        request_data.max_tokens = 65535

    setattr(request_data, "top_k", 64)
    trace.mark("preprocessing_complete")

    model = request_data.model
    is_streaming = bool(getattr(request_data, "stream", False))
    use_fake_streaming = is_fake_streaming_model(model)
    if use_fake_streaming:
        request_data.model = get_base_model_from_feature_model(model)
        model = request_data.model
        if trace:
            trace.model = model
    message_count = len(getattr(request_data, "messages", []) or [])

    log.info(
        f"[ANTHROPIC_REQ_DIAG] stream={1 if is_streaming else 0} model={model} "
        f"max_tokens={getattr(request_data, 'max_tokens', None)} messages={message_count}"
    )

    if is_streaming:
        use_fake_route, stream_route_reason = await _should_use_fake_streaming(
            model, use_fake_streaming
        )
        _annotate_stream_route_metadata(
            trace,
            model=model,
            requested=True,
            use_fake_route=use_fake_route,
            reason=stream_route_reason,
        )
        if use_fake_route:
            log.info(f"使用假流式模式（{stream_route_reason}）")
            request_data.stream = False
            openai_stream = await fake_stream_response_for_assembly(request_data, trace=trace)
        else:
            log.info("使用真实流式模式（自动路由）")
            async def request_provider():
                return await send_assembly_request(request_data, True, trace=trace)

            upstream_response = await request_provider()
            openai_stream = await convert_streaming_response(
                upstream_response,
                model,
                trace=trace,
                request_provider=request_provider,
            )

        return await _convert_openai_stream_to_anthropic(openai_stream, model)

    upstream_response = await send_assembly_request(request_data, False, trace=trace)
    response_status = getattr(upstream_response, "status_code", 200)
    if response_status >= 400:
        parsed_error = None
        try:
            raw = _extract_response_text(upstream_response)
            parsed_error = json.loads(raw)
        except Exception:
            parsed_error = None

        if trace:
            try:
                await tracker.end_trace(trace.trace_id, success=False)
            except Exception:
                pass

        message = "Upstream request failed"
        if isinstance(parsed_error, dict):
            if isinstance(parsed_error.get("error"), dict):
                message = str(parsed_error["error"].get("message") or message)
            else:
                message = str(parsed_error.get("message") or message)

        return JSONResponse(
            content=openai_error_to_anthropic_error(
                response_status, parsed_error, fallback_message=message
            ),
            status_code=response_status,
        )

    text = _extract_response_text(upstream_response)
    parsed = _parse_response_json(text, upstream_response)
    if isinstance(parsed, dict):
        upstream_shape = _summarize_upstream_response_shape(parsed)
        log.info(
            f"[ANTHROPIC_UPSTREAM_SHAPE] stream=0 model={model} "
            f"choices={upstream_shape.get('choices_count', 0)} "
            f"shape={json.dumps(upstream_shape.get('choice_shapes', []), ensure_ascii=False)}"
        )
        openai_response = assembly_response_to_openai(parsed, model)
    else:
        openai_response = _build_openai_fallback_text_response(model, text)

    non_stream_diag = _extract_openai_response_diagnostics(openai_response)
    log.info(
        f"[ANTHROPIC_DIAG] stream=0 model={model} finish_reason={non_stream_diag['finish_reason']} "
        f"tool_calls_count={non_stream_diag['tool_calls_count']}"
    )

    anthropic_response = openai_response_to_anthropic(openai_response, fallback_model=model)

    usage_metrics = _extract_usage_metrics(openai_response.get("usage", {}) if isinstance(openai_response, dict) else {})
    if trace and isinstance(openai_response, dict):
        annotate_cache_usage_metadata(
            trace.metadata,
            openai_response.get("usage", {}),
            source="anthropic_non_stream",
        )

    if trace:
        trace.mark("conversion_complete")
        trace.mark("first_chunk_sent")
        await tracker.end_trace(
            trace.trace_id,
            completion_tokens=usage_metrics["completion_tokens"],
            prompt_tokens=usage_metrics["prompt_tokens"],
            cached_tokens=usage_metrics["cached_tokens"],
            total_tokens=usage_metrics["total_tokens"],
            cache_creation_5m_tokens=usage_metrics.get("cache_creation_5m_tokens", 0),
            cache_creation_1h_tokens=usage_metrics.get("cache_creation_1h_tokens", 0),
            success=True,
        )

    return JSONResponse(content=anthropic_response)


@router.post("/v1/messages/count_tokens")
async def anthropic_count_tokens(
    request: Request,
):
    """Anthropic count_tokens compatibility endpoint."""
    try:
        await authenticate_anthropic_request(request)
    except HTTPException as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                e.status_code, {"message": str(e.detail)}, fallback_message=str(e.detail)
            ),
            status_code=e.status_code,
        )

    try:
        raw_data = await request.json()
    except Exception as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                400, {"message": f"Invalid JSON: {str(e)}"}, fallback_message="Invalid JSON"
            ),
            status_code=400,
        )

    try:
        openai_payload = convert_claude_request_to_openai(raw_data)
    except Exception as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                400, {"message": str(e)}, fallback_message="Invalid request"
            ),
            status_code=400,
        )
    if isinstance(openai_payload.get("model"), str):
        openai_payload["model"] = normalize_model_id(openai_payload["model"])

    # 多租户：对 user token 强制模型白名单/禁用/过期（不消费配额——count_tokens 是免费本地估算）
    try:
        await enforce_token_quota(request, str(openai_payload.get("model", "")), consume=False)
    except HTTPException as e:
        return JSONResponse(
            content=openai_error_to_anthropic_error(
                e.status_code, {"message": str(e.detail)}, fallback_message=str(e.detail)
            ),
            status_code=e.status_code,
        )

    messages = openai_payload.get("messages", [])
    input_tokens = estimate_input_tokens(messages)
    return JSONResponse(content={"input_tokens": input_tokens})

@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    token: str = Depends(authenticate)
):
    """处理OpenAI格式的聊天完成请求"""
    
    # 性能追踪：开始追踪
    trace_id = str(uuid.uuid4())
    tracker = await get_performance_tracker()
    trace = tracker.start_trace(trace_id, "pending")  # 模型名稍后更新
    
    # 标记认证完成
    trace.mark("auth_complete")
    
    # 获取原始请求数据
    try:
        raw_data = await request.json()
        # 记录请求中的所有参数（排除 messages 内容以减少日志量）
        params_to_log = {k: v for k, v in raw_data.items() if k != 'messages'}
        log.info(f"Request params: model={raw_data.get('model')}, stream={raw_data.get('stream')}, extra_keys={list(params_to_log.keys())}")
        log.debug(f"Full request params (excluding messages): {json.dumps(params_to_log, ensure_ascii=False)[:500]}...")
    except Exception as e:
        log.error(f"Failed to parse JSON request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    
    # 创建请求对象
    try:
        request_data = ChatCompletionRequest(**raw_data)
        _normalize_request_model_ids(request_data)
        # 更新追踪的模型名称
        trace.model = request_data.model
        
        log.debug(f"Request validated - model: {request_data.model}, messages: {len(request_data.messages)}, stream: {getattr(request_data, 'stream', False)}")
        
        # 详细记录接收到的消息结构
        log.debug(f"Received messages structure:")
        for i, m in enumerate(request_data.messages):
            role = getattr(m, "role", "unknown")
            has_tool_calls = bool(getattr(m, "tool_calls", None))
            has_tool_call_id = bool(getattr(m, "tool_call_id", None))
            content_preview = str(getattr(m, "content", ""))[:50]
            log.debug(f"  [{i}] role={role}, tool_calls={has_tool_calls}, tool_call_id={has_tool_call_id}, content={content_preview}...")
    except Exception as e:
        log.error(f"Request validation failed: {e}")
        raise HTTPException(status_code=400, detail=f"Request validation error: {str(e)}")

    # 多租户：对 user token 强制模型白名单 + 配额（master 不受限）。放在校验之外，
    # 避免 429/403 被上面的 except 包装成 400。
    await enforce_token_quota(
        request,
        request_data.model,
        fallback_models=_extract_fallback_model_ids(getattr(request_data, "fallbacks", None)),
    )

    # 健康检查
    if (len(request_data.messages) == 1 and
        getattr(request_data.messages[0], "role", None) == "user" and
        getattr(request_data.messages[0], "content", None) == "Hi"):
        return JSONResponse(content={
            "choices": [{"message": {"role": "assistant", "content": "amb2api正常工作中"}}]
        })
    
    # 限制max_tokens
    if getattr(request_data, "max_tokens", None) is not None and request_data.max_tokens > 65535:
        request_data.max_tokens = 65535
    
    # Max Tokens 自适应处理
    try:
        from ..storage.storage_adapter import get_storage_adapter
        from ..models.model_limits import get_model_max_tokens
        
        adapter = await get_storage_adapter()
        max_tokens_mode = await adapter.get_config("max_tokens_mode", "off")
        
        if max_tokens_mode != "off":
            model_max = await get_model_max_tokens(request_data.model)
            
            if max_tokens_mode == "high":
                target_max_tokens = model_max
            elif max_tokens_mode == "medium":
                target_max_tokens = model_max // 2
            else:  # low
                target_max_tokens = min(4096, model_max)
            
            original_max_tokens = getattr(request_data, "max_tokens", None)
            request_data.max_tokens = target_max_tokens
            log.info(f"Max tokens adaptive: mode={max_tokens_mode}, model_max={model_max}, original={original_max_tokens}, target={target_max_tokens}")
    except Exception as e:
        log.warning(f"Max tokens adaptive processing failed: {e}")
        
    # 覆写 top_k 为 64
    setattr(request_data, "top_k", 64)

    # 过滤空消息（但保留有 tool_calls 的消息和 assistant/tool 消息）
    filtered_messages = []
    for m in request_data.messages:
        content = getattr(m, "content", None)
        tool_calls = getattr(m, "tool_calls", None)
        role = getattr(m, "role", "unknown")
        
        # 如果有 tool_calls，即使 content 为空也保留
        if tool_calls:
            log.debug(f"Keeping message with tool_calls: role={role}, content={'[empty]' if not content else content[:50]+'...'}")
            filtered_messages.append(m)
            continue
        
        # 保留 assistant 和 tool 消息，即使 content 为空
        # 这对于多轮对话很重要
        if role in ["assistant", "tool"]:
            filtered_messages.append(m)
            continue
        
        # 对于其他角色，检查 content 是否有效
        if content:
            if isinstance(content, str) and content.strip():
                filtered_messages.append(m)
            elif isinstance(content, list) and len(content) > 0:
                has_valid_content = False
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text" and part.get("text", "").strip():
                            has_valid_content = True
                            break
                        elif part.get("type") == "image_url" and part.get("image_url", {}).get("url"):
                            has_valid_content = True
                            break
                if has_valid_content:
                    filtered_messages.append(m)
    
    request_data.messages = filtered_messages
    
    log.debug(f"After filtering: {len(request_data.messages)} messages")
    for i, m in enumerate(request_data.messages):
        role = getattr(m, "role", "unknown")
        has_tool_calls = bool(getattr(m, "tool_calls", None))
        content_preview = str(getattr(m, "content", ""))[:50]
        log.debug(f"  [{i}] role={role}, has_tool_calls={has_tool_calls}, content={content_preview}...")
    
    # AssemblyAI 支持完整的 OpenAI 协议，不需要重建消息
    
    # 优化消息历史，避免超出 token 限制
    from ..transform.message_optimizer import optimize_messages
    try:
        optimized_messages = optimize_messages(request_data.messages)
        request_data.messages = optimized_messages
        log.debug(f"Messages optimized: {len(filtered_messages)} -> {len(optimized_messages)}")
    except Exception as e:
        log.warning(f"Message optimization failed: {e}, using original messages")
    
    # 标记预处理完成
    trace.mark("preprocessing_complete")
    
    # 处理模型名称和功能检测
    model = request_data.model
    use_fake_streaming = is_fake_streaming_model(model)
    if use_fake_streaming:
        request_data.model = get_base_model_from_feature_model(model)
        model = request_data.model
        if trace:
            trace.model = model

    # 特征前缀已在上方剥离，其余模型名直接透传给 AssemblyAI。

    # 发送到 AssemblyAI（非流式）
    is_streaming = getattr(request_data, "stream", False)
    if is_streaming:
        use_fake_route, stream_route_reason = await _should_use_fake_streaming(
            model, use_fake_streaming
        )
        _annotate_stream_route_metadata(
            trace,
            model=model,
            requested=True,
            use_fake_route=use_fake_route,
            reason=stream_route_reason,
        )
        if use_fake_route:
            log.info(f"使用假流式模式（{stream_route_reason}）")
            request_data.stream = False
            return await fake_stream_response_for_assembly(request_data, trace=trace)

        log.info("使用真实流式模式（自动路由）")
        # 真实流式模式：首包前支持 bootstrap 重试，首包后不重试
        async def request_provider():
            return await send_assembly_request(request_data, True, trace=trace)

        response, bootstrap_retries_override = await _request_native_stream_with_header_bootstrap_retries(
            request_provider,
            trace=trace,
        )
        response_status = getattr(response, "status_code", 200)
        if response_status >= 400:
            return await _forward_openai_error_response(
                response,
                response_status,
                trace=trace,
                tracker=tracker,
            )
        return await convert_streaming_response(
            response,
            model,
            trace=trace,
            request_provider=request_provider,
            bootstrap_retries_override=bootstrap_retries_override,
        )
    
    log.info(f"REQ model={model}")
    log.debug(f"Sending request to AssemblyAI - stream: {is_streaming}, messages: {len(request_data.messages)}")
    
    response = await send_assembly_request(request_data, False, trace=trace)

    # 上游或网关已返回错误响应时，直接透传状态码和错误体
    response_status = getattr(response, "status_code", 200)
    if response_status >= 400:
        return await _forward_openai_error_response(
            response,
            response_status,
            trace=trace,
            tracker=tracker,
        )
    
    # 性能追踪：上游响应完成
    if trace:
        trace.mark("upstream_first_byte")
        trace.mark("upstream_response_complete")
    
    # 如果是流式响应，直接返回
    if is_streaming:
        log.debug(f"Converting to streaming response for model: {model}")
        return await convert_streaming_response(response, model, trace=trace)
    
    # 转换非流式响应（AssemblyAI → OpenAI）
    usage_metrics = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "cache_creation_5m_tokens": 0,
        "cache_creation_1h_tokens": 0,
        "total_tokens": 0,
    }
    try:
        try:
            if hasattr(response, 'text') and isinstance(getattr(response, 'text'), str):
                text = response.text
            elif hasattr(response, 'body'):
                body = response.body
                text = body.decode('utf-8', errors='replace') if isinstance(body, bytes) else str(body)
            elif hasattr(response, 'content'):
                content = response.content
                text = content.decode('utf-8', errors='replace') if isinstance(content, bytes) else str(content)
            else:
                text = str(response)
        except Exception as de:
            log.warning(f"Response decode failed: {de}")
            text = str(response)
        parsed = None
        try:
            parsed = json.loads(text.strip())
        except Exception:
            if 'data:' in text:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                for l in reversed(lines):
                    if not l.startswith('data:'):
                        continue
                    payload = l[5:].strip()
                    if payload == '[DONE]':
                        continue
                    try:
                        parsed = json.loads(payload)
                        break
                    except Exception:
                        pass
            if parsed is None and hasattr(response, 'json'):
                try:
                    parsed = response.json()
                except Exception:
                    parsed = None

        if isinstance(parsed, dict):
            # 检查是否是错误响应
            if 'code' in parsed and parsed.get('code') != 200:
                error_message = parsed.get('message', 'Unknown error')
                log.error(f"AssemblyAI returned error: {parsed.get('code')} - {error_message}")
                raise HTTPException(
                    status_code=parsed.get('code', 500),
                    detail=f"AssemblyAI error: {error_message}"
                )
            
            # 提取 token 数量
            parsed_usage = parsed.get('usage', {})
            usage_metrics = _extract_usage_metrics(parsed_usage)
            if trace:
                annotate_cache_usage_metadata(
                    trace.metadata,
                    parsed_usage,
                    source="non_stream_upstream",
                )
            
            # AssemblyAI 返回 OpenAI 格式，直接使用或进行微调
            openai_response = assembly_response_to_openai(parsed, model)
            converted_usage_metrics = _extract_usage_metrics(openai_response.get("usage", {}))
            if converted_usage_metrics["total_tokens"] > 0 or converted_usage_metrics["cached_tokens"] > 0:
                usage_metrics = converted_usage_metrics
        else:
            openai_response = {
                "id": str(uuid.uuid4()),
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text.strip()},
                    "finish_reason": "stop"
                }]
            }
        
        # 性能追踪：格式转换完成
        if trace:
            trace.mark("conversion_complete")
            trace.mark("first_chunk_sent")
        
        # 如果最终choices为空，构造一个兜底消息避免前端空白
        try:
            if isinstance(openai_response, dict):
                ch = openai_response.get('choices')
                if isinstance(ch, list) and len(ch) == 0:
                    fallback_content = ''
                    if isinstance(parsed, dict):
                        fallback_content = str(parsed.get('output_text') or parsed.get('text') or '')
                    if not fallback_content:
                        fallback_content = text.strip()
                    openai_response['choices'] = [{
                        'index': 0,
                        'message': {'role': 'assistant', 'content': fallback_content},
                        'finish_reason': 'stop'
                    }]
        except Exception:
            pass

        log.info(f"RES model={model} status=OK")
        log.debug(f"RES Details - Converted response: {json.dumps(openai_response, ensure_ascii=False)[:1000]}...")
        
        # 性能追踪：响应完成
        if trace:
            await tracker.end_trace(
                trace.trace_id,
                completion_tokens=usage_metrics["completion_tokens"],
                prompt_tokens=usage_metrics["prompt_tokens"],
                cached_tokens=usage_metrics["cached_tokens"],
                total_tokens=usage_metrics["total_tokens"],
                cache_creation_5m_tokens=usage_metrics.get("cache_creation_5m_tokens", 0),
                cache_creation_1h_tokens=usage_metrics.get("cache_creation_1h_tokens", 0),
                success=True,
            )

        return JSONResponse(content=openai_response)
    except Exception as e:
        try:
            sample = (text[:200] + '...') if isinstance(text, str) and len(text) > 200 else text
            log.error(f"RES model={model} status=FAIL conversion_error sample={sample}")
            log.debug(f"RES Details - Conversion error: {str(e)}, Full text: {text[:500]}...")
        except Exception:
            log.error(f"RES model={model} status=FAIL conversion_error")
        raise HTTPException(status_code=500, detail="Response conversion failed")


@router.post("/v1/responses")
async def responses_api(
    request: Request,
    token: str = Depends(authenticate),
):
    """Compatibility bridge for clients that use OpenAI's Responses API."""
    try:
        raw_data = await request.json()
    except Exception as e:
        log.error(f"Failed to parse Responses API JSON request: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")

    if not isinstance(raw_data, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    try:
        chat_payload = _responses_request_to_chat_payload(raw_data)
    except _ResponsesCompatibilityError as e:
        log.warning(f"Responses API compatibility unsupported request: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    if not chat_payload.get("model"):
        raise HTTPException(status_code=400, detail="model is required")
    if not chat_payload.get("messages"):
        raise HTTPException(status_code=400, detail="input is required")

    log.info(
        "Responses API compatibility route: "
        f"model={chat_payload.get('model')}, stream={chat_payload.get('stream')}, "
        f"messages={len(chat_payload.get('messages') or [])}"
    )

    chat_response = await chat_completions(_JsonRequestProxy(request, chat_payload), token)
    response_status = getattr(chat_response, "status_code", 200)
    if response_status >= 400:
        return chat_response

    model = normalize_model_id(str(chat_payload.get("model") or ""))
    if isinstance(chat_response, StreamingResponse):
        return _chat_stream_to_responses_stream(chat_response, model)

    parsed = _json_response_to_payload(chat_response)
    if parsed is None:
        log.error("Responses API compatibility route failed to parse chat response")
        raise HTTPException(status_code=500, detail="Response conversion failed")

    return JSONResponse(content=_chat_completion_to_response_payload(parsed, model, request_payload=raw_data))


@router.post("/v1")
@router.post("/v1/")
async def chat_completions_v1_alias(
    request: Request,
    token: str = Depends(authenticate),
):
    """Compatibility alias for clients that POST chat payloads to the base /v1 URL."""
    return await chat_completions(request, token)
