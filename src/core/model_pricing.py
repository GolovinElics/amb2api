"""LLM Gateway model pricing and per-request cost helpers.

Rates are USD per one million tokens. The built-in catalog mirrors the public
AssemblyAI pricing table and is used as a synchronous fallback for request
trace cost accounting; account pages may still refresh live rates from the
official pricing page.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Dict, Iterable, List, Optional


TOKENS_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class ModelPricing:
    model: str
    provider: str
    input_per_million: float
    output_per_million: float
    aliases: tuple[str, ...] = ()
    cached_input_per_million: Optional[float] = None
    cache_creation_5m_per_million: Optional[float] = None
    cache_creation_1h_per_million: Optional[float] = None
    source: str = "assemblyai_official_pricing"


def _normalize_model_key(name: Any) -> str:
    text = str(name or "").strip().lower()
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    text = re.sub(r"\([^)]*\)", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _cache_rate(provider: str, input_rate: float, model: str = "") -> Optional[float]:
    provider_key = str(provider or "").lower()
    model_key = _normalize_model_key(model)
    if provider_key == "kimi" or "k2.5" in model_key or "kimi" in model_key:
        return 0.10
    if provider_key in {"openai", "anthropic", "google", "qwen"}:
        return round(float(input_rate) * 0.1, 8)
    return round(float(input_rate) * 0.1, 8) if input_rate else None


def _claude_5m_rate(provider: str, input_rate: float) -> Optional[float]:
    if str(provider or "").lower() != "anthropic":
        return None
    return round(float(input_rate) * 1.25, 8)


def _claude_1h_rate(provider: str, input_rate: float) -> Optional[float]:
    if str(provider or "").lower() != "anthropic":
        return None
    return round(float(input_rate) * 2.0, 8)


def _make_pricing(
    model: str,
    provider: str,
    input_rate: float,
    output_rate: float,
    *aliases: str,
) -> ModelPricing:
    return ModelPricing(
        model=model,
        provider=provider,
        input_per_million=float(input_rate),
        output_per_million=float(output_rate),
        aliases=tuple(aliases),
        cached_input_per_million=_cache_rate(provider, float(input_rate), model),
        cache_creation_5m_per_million=_claude_5m_rate(provider, float(input_rate)),
        cache_creation_1h_per_million=_claude_1h_rate(provider, float(input_rate)),
    )


_CATALOG: tuple[ModelPricing, ...] = (
    _make_pricing("GPT-5.5", "openai", 5.00, 30.00, "gpt-5.5", "openai/gpt-5.5"),
    _make_pricing("GPT-5.2", "openai", 1.75, 14.00, "gpt-5.2", "openai/gpt-5.2"),
    _make_pricing("GPT-5.1", "openai", 1.25, 10.00, "gpt-5.1", "openai/gpt-5.1"),
    _make_pricing("GPT-5", "openai", 1.25, 10.00, "gpt-5", "openai/gpt-5"),
    _make_pricing("GPT-5-Mini", "openai", 0.25, 2.00, "gpt-5-mini", "gpt5mini"),
    _make_pricing("GPT-5 Nano", "openai", 0.05, 0.40, "gpt-5-nano", "gpt5nano"),
    _make_pricing("GPT 4.1", "openai", 2.00, 8.00, "gpt-4.1", "gpt41"),
    _make_pricing("ChatGPT 4o", "openai", 5.00, 15.00, "chatgpt-4o", "chatgpt-4o-latest", "gpt-4o"),
    _make_pricing("gpt-oss-20b", "openai", 0.07, 0.30, "gpt-oss-20b"),
    _make_pricing("gpt-oss-120b", "openai", 0.15, 0.60, "gpt-oss-120b"),
    _make_pricing("Claude 4.8 Opus", "anthropic", 5.00, 25.00, "claude-opus-4-8"),
    _make_pricing("Claude 4.7 Opus", "anthropic", 5.00, 25.00, "claude-opus-4-7"),
    _make_pricing("Claude 4.6 Opus", "anthropic", 5.00, 25.00, "claude-opus-4-6"),
    _make_pricing("Claude 4.5 Opus", "anthropic", 5.00, 25.00, "claude-opus-4-5-20251101", "claude-opus-4-5"),
    _make_pricing("Claude 4.6 Sonnet", "anthropic", 3.00, 15.00, "claude-sonnet-4-6"),
    _make_pricing("Claude 4.5 Sonnet", "anthropic", 3.00, 15.00, "claude-sonnet-4-5-20250929", "claude-sonnet-4-5"),
    _make_pricing("Claude 4.5 Haiku", "anthropic", 1.00, 5.00, "claude-haiku-4-5-20251001", "claude-haiku-4-5"),
    _make_pricing("Gemini 3.5 Flash", "google", 1.50, 9.00, "gemini-3.5-flash"),
    _make_pricing("Gemini 3 Flash", "google", 0.50, 3.00, "gemini-3-flash", "gemini-3-flash-preview"),
    _make_pricing("Gemini 3.1 Flash Lite", "google", 0.25, 1.50, "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview"),
    _make_pricing("Gemini 2.5 Flash", "google", 0.30, 2.50, "gemini-2.5-flash"),
    _make_pricing("Gemini 2.5 Flash Lite", "google", 0.10, 0.40, "gemini-2.5-flash-lite"),
    _make_pricing("Gemini 2.5 Pro", "google", 1.25, 10.00, "gemini-2.5-pro"),
    _make_pricing("Qwen3 Next 80B A3B", "qwen", 0.15, 1.20, "qwen3-next-80b-a3b"),
    _make_pricing("Qwen3 32B", "qwen", 0.15, 0.60, "qwen3-32b", "qwen3-32B"),
    _make_pricing("Kimi K2.5", "kimi", 0.60, 3.00, "kimi-k2.5"),
)


_PRICING_BY_KEY: Dict[str, ModelPricing] = {}
for _entry in _CATALOG:
    for _name in (_entry.model, *_entry.aliases):
        _PRICING_BY_KEY[_normalize_model_key(_name)] = _entry
_PRICING_OVERRIDES: Dict[str, ModelPricing] = {}


def get_model_pricing(model: Any) -> Optional[ModelPricing]:
    key = _normalize_model_key(model)
    if not key:
        return None
    if key in _PRICING_OVERRIDES:
        return _PRICING_OVERRIDES[key]
    if key in _PRICING_BY_KEY:
        return _PRICING_BY_KEY[key]

    for known_key, pricing in _PRICING_OVERRIDES.items():
        if known_key and (key in known_key or known_key in key):
            return pricing
    for known_key, pricing in _PRICING_BY_KEY.items():
        if known_key and (key in known_key or known_key in key):
            return pricing
    return None


def update_pricing_overrides_from_rates(
    input_rates: Iterable[Dict[str, Any]],
    output_rates: Iterable[Dict[str, Any]],
) -> int:
    """Update in-process pricing from Dashboard/official rate payloads.

    The request hot path stays network-free and falls back to the built-in
    AssemblyAI table, while account-rate refreshes can feed newer prices into
    later trace calculations in the same process.
    """
    output_by_key = {
        _normalize_model_key(item.get("model")): item
        for item in (output_rates or [])
        if isinstance(item, dict) and _normalize_model_key(item.get("model"))
    }
    updated = 0
    for item in input_rates or []:
        if not isinstance(item, dict):
            continue
        model = str(item.get("model") or "").strip()
        key = _normalize_model_key(model)
        if not model or not key:
            continue
        input_rate = _finite_float(item.get("rate"), default=0.0)
        if input_rate <= 0:
            continue
        output_item = output_by_key.get(key) or {}
        output_rate = _finite_float(output_item.get("rate"), default=0.0)
        if output_rate < 0:
            output_rate = 0.0

        provider = _provider_from_model(model)
        cached_rate = _optional_finite_rate(item.get("cached_input_rate"))
        cache_5m = _optional_finite_rate(item.get("cache_creation_5m_rate"))
        cache_1h = _optional_finite_rate(item.get("cache_creation_1h_rate"))

        pricing = ModelPricing(
            model=model,
            provider=provider,
            input_per_million=input_rate,
            output_per_million=output_rate,
            aliases=(model,),
            cached_input_per_million=cached_rate if cached_rate is not None else _cache_rate(provider, input_rate, model),
            cache_creation_5m_per_million=cache_5m if cache_5m is not None else _claude_5m_rate(provider, input_rate),
            cache_creation_1h_per_million=cache_1h if cache_1h is not None else _claude_1h_rate(provider, input_rate),
            source=str(item.get("price_source") or output_item.get("price_source") or "runtime_rates"),
        )
        _PRICING_OVERRIDES[key] = pricing
        updated += 1
    return updated


def _provider_from_model(model: Any) -> str:
    key = _normalize_model_key(model)
    if "claude" in key:
        return "anthropic"
    if "gemini" in key:
        return "google"
    if "kimi" in key:
        return "kimi"
    if "qwen" in key:
        return "qwen"
    if "gpt" in key or "chatgpt" in key or key.startswith("o"):
        return "openai"
    return "unknown"


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _optional_finite_rate(value: Any) -> Optional[float]:
    if value is None:
        return None
    parsed = _finite_float(value, default=-1.0)
    return parsed if parsed >= 0 else None


def _region_multiplier(model_region: Any) -> float:
    region = str(model_region or "").strip().lower()
    if region in {"us", "usa", "eu", "europe", "in-region", "regional"}:
        return 1.1
    return 1.0


def _money(tokens: int, rate_per_million: Optional[float], multiplier: float) -> float:
    if not tokens or not rate_per_million:
        return 0.0
    return tokens * float(rate_per_million) * multiplier / TOKENS_PER_MILLION


def _non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _rate_dict(pricing: Optional[ModelPricing], model: Any, region_multiplier: float) -> Dict[str, Any]:
    if pricing is None:
        provider = _provider_from_model(model)
        return {
            "model": str(model or ""),
            "provider": provider,
            "source": "unknown",
            "unit": "1M tokens",
            "region_multiplier": region_multiplier,
            "input_per_million": 0.0,
            "cached_input_per_million": 0.0,
            "cache_creation_5m_per_million": 0.0,
            "cache_creation_1h_per_million": 0.0,
            "output_per_million": 0.0,
        }

    return {
        "model": pricing.model,
        "provider": pricing.provider,
        "source": pricing.source,
        "unit": "1M tokens",
        "region_multiplier": region_multiplier,
        "input_per_million": pricing.input_per_million * region_multiplier,
        "cached_input_per_million": (pricing.cached_input_per_million or 0.0) * region_multiplier,
        "cache_creation_5m_per_million": (pricing.cache_creation_5m_per_million or 0.0) * region_multiplier,
        "cache_creation_1h_per_million": (pricing.cache_creation_1h_per_million or 0.0) * region_multiplier,
        "output_per_million": pricing.output_per_million * region_multiplier,
    }


def calculate_token_cost(
    model: Any,
    *,
    prompt_tokens: Any = 0,
    completion_tokens: Any = 0,
    cached_tokens: Any = 0,
    cache_creation_5m_tokens: Any = 0,
    cache_creation_1h_tokens: Any = 0,
    model_region: Any = "",
) -> Dict[str, Any]:
    prompt = _non_negative_int(prompt_tokens)
    completion = _non_negative_int(completion_tokens)
    cached = min(_non_negative_int(cached_tokens), prompt)
    creation_5m = min(_non_negative_int(cache_creation_5m_tokens), max(prompt - cached, 0))
    creation_1h = min(_non_negative_int(cache_creation_1h_tokens), max(prompt - cached - creation_5m, 0))
    uncached = max(prompt - cached - creation_5m - creation_1h, 0)

    pricing = get_model_pricing(model)
    multiplier = _region_multiplier(model_region)
    input_rate = pricing.input_per_million if pricing else 0.0
    output_rate = pricing.output_per_million if pricing else 0.0
    cached_rate = pricing.cached_input_per_million if pricing else 0.0
    creation_5m_rate = pricing.cache_creation_5m_per_million if pricing else 0.0
    creation_1h_rate = pricing.cache_creation_1h_per_million if pricing else 0.0

    input_cost = _money(uncached, input_rate, multiplier)
    cache_read_cost = _money(cached, cached_rate, multiplier)
    cache_creation_5m_cost = _money(creation_5m, creation_5m_rate or input_rate, multiplier)
    cache_creation_1h_cost = _money(creation_1h, creation_1h_rate or input_rate, multiplier)
    output_cost = _money(completion, output_rate, multiplier)
    total_cost = input_cost + cache_read_cost + cache_creation_5m_cost + cache_creation_1h_cost + output_cost

    standard_input_cost = _money(prompt, input_rate, multiplier)
    actual_input_cost = input_cost + cache_read_cost + cache_creation_5m_cost + cache_creation_1h_cost

    return {
        "input_cost": input_cost,
        "cache_read_cost": cache_read_cost,
        "cache_creation_5m_cost": cache_creation_5m_cost,
        "cache_creation_1h_cost": cache_creation_1h_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "standard_input_cost_without_cache": standard_input_cost,
        "cache_discount_savings": standard_input_cost - actual_input_cost,
        "tokens": {
            "uncached_input_tokens": uncached,
            "cached_tokens": cached,
            "cache_creation_5m_tokens": creation_5m,
            "cache_creation_1h_tokens": creation_1h,
            "completion_tokens": completion,
        },
        "pricing": _rate_dict(pricing, model, multiplier),
    }


def minimum_cacheable_tokens(model: Any) -> Optional[int]:
    key = _normalize_model_key(model)
    if "claudeopus" in key or ("claude" in key and "opus" in key):
        return 4096
    if "claudesonnet46" in key or ("claude" in key and "sonnet" in key and "46" in key):
        return 2048
    if "claudesonnet45" in key or ("claude" in key and "sonnet" in key and "45" in key):
        return 1024
    if "claudehaiku45" in key or ("claude" in key and "haiku" in key and "45" in key):
        return 4096
    if "gpt" in key or "chatgpt" in key or key.startswith("o"):
        return 1024
    if "gemini" in key or "kimi" in key or "qwen" in key:
        return 1024
    return None


def cache_status_for_usage(
    model: Any,
    *,
    prompt_tokens: Any = 0,
    cached_tokens: Any = 0,
    cache_creation_5m_tokens: Any = 0,
    cache_creation_1h_tokens: Any = 0,
) -> Dict[str, Any]:
    prompt = _non_negative_int(prompt_tokens)
    cached = _non_negative_int(cached_tokens)
    creation = _non_negative_int(cache_creation_5m_tokens) + _non_negative_int(cache_creation_1h_tokens)
    minimum = minimum_cacheable_tokens(model)
    provider = _provider_from_model(model)

    if cached > 0:
        status = "hit"
        message = f"缓存命中 {cached} tokens，已按缓存读取价格估算。"
    elif creation > 0:
        status = "created"
        message = f"本次写入缓存 {creation} tokens；后续相同前缀命中后才会显示缓存读取。"
    elif minimum and prompt < minimum:
        status = "too_short"
        message = f"输入少于 {minimum} tokens，低于该模型可缓存阈值，官方会返回 cached_tokens=0。"
    else:
        status = "miss"
        message = "未命中缓存；通常是稳定前缀未复用、路由未落到同一缓存组，或缓存已过期。"

    return {
        "status": status,
        "message": message,
        "minimum_cacheable_tokens": minimum,
        "provider": provider,
    }


def _rate_item(pricing: ModelPricing, direction: str) -> Dict[str, Any]:
    rate = pricing.input_per_million if direction == "input" else pricing.output_per_million
    item = {
        "model": pricing.model,
        "rate": rate,
        "unit": "1M tokens",
        "price_source": pricing.source,
    }
    if direction == "input":
        item = enrich_llm_input_rate_item(item)
    return item


def llm_gateway_rate_items() -> Dict[str, List[Dict[str, Any]]]:
    return {
        "llm_gateway_input": [_rate_item(pricing, "input") for pricing in _CATALOG],
        "llm_gateway_output": [_rate_item(pricing, "output") for pricing in _CATALOG],
    }


def enrich_llm_input_rate_item(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item)
    model = out.get("model")
    provider = _provider_from_model(model)
    input_rate = _finite_float(out.get("rate"), default=0.0)
    if input_rate < 0:
        input_rate = 0.0

    out["cached_input_rate"] = _cache_rate(provider, input_rate, str(model or ""))
    out["cache_creation_5m_rate"] = _claude_5m_rate(provider, input_rate)
    out["cache_creation_1h_rate"] = _claude_1h_rate(provider, input_rate)
    return out


def enrich_llm_input_rates(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [enrich_llm_input_rate_item(item) for item in items or []]
