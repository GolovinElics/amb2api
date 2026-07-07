import math

from src.core.model_pricing import (
    cache_status_for_usage,
    calculate_token_cost,
    get_model_pricing,
    llm_gateway_rate_items,
    update_pricing_overrides_from_rates,
)


def test_get_model_pricing_matches_prefixed_gateway_model_alias():
    pricing = get_model_pricing("openai/gpt-5.5")

    assert pricing is not None
    assert pricing.model == "GPT-5.5"
    assert pricing.input_per_million == 5.0
    assert pricing.output_per_million == 30.0
    assert pricing.cached_input_per_million == 0.5


def test_calculate_token_cost_splits_cached_openai_input_tokens():
    cost = calculate_token_cost(
        "gpt-5.5",
        prompt_tokens=2000,
        completion_tokens=500,
        cached_tokens=1000,
    )

    assert cost["pricing"]["model"] == "GPT-5.5"
    assert cost["tokens"]["uncached_input_tokens"] == 1000
    assert math.isclose(cost["input_cost"], 0.005, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["cache_read_cost"], 0.0005, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["output_cost"], 0.015, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["total_cost"], 0.0205, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["cache_discount_savings"], 0.0045, rel_tol=0, abs_tol=1e-12)


def test_calculate_token_cost_uses_claude_cache_write_prices():
    cost = calculate_token_cost(
        "claude-sonnet-4-6",
        prompt_tokens=3000,
        completion_tokens=100,
        cached_tokens=1000,
        cache_creation_5m_tokens=500,
        cache_creation_1h_tokens=250,
    )

    assert cost["pricing"]["model"] == "Claude 4.6 Sonnet"
    assert cost["tokens"]["uncached_input_tokens"] == 1250
    assert math.isclose(cost["input_cost"], 0.00375, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["cache_read_cost"], 0.0003, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["cache_creation_5m_cost"], 0.001875, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["cache_creation_1h_cost"], 0.0015, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(cost["output_cost"], 0.0015, rel_tol=0, abs_tol=1e-12)


def test_calculate_token_cost_applies_in_region_uplift():
    global_cost = calculate_token_cost("gpt-5.1", prompt_tokens=1000, completion_tokens=1000)
    us_cost = calculate_token_cost(
        "gpt-5.1",
        prompt_tokens=1000,
        completion_tokens=1000,
        model_region="us",
    )

    assert math.isclose(us_cost["total_cost"], global_cost["total_cost"] * 1.1, rel_tol=0, abs_tol=1e-12)
    assert us_cost["pricing"]["region_multiplier"] == 1.1


def test_cache_status_explains_short_uncached_openai_prompts():
    status = cache_status_for_usage(
        "gpt-4.1",
        prompt_tokens=14,
        cached_tokens=0,
        cache_creation_5m_tokens=0,
        cache_creation_1h_tokens=0,
    )

    assert status["status"] == "too_short"
    assert status["minimum_cacheable_tokens"] == 1024
    assert "少于" in status["message"]


def test_cache_status_reports_cache_hit():
    status = cache_status_for_usage(
        "gpt-4.1",
        prompt_tokens=2048,
        cached_tokens=1024,
        cache_creation_5m_tokens=0,
        cache_creation_1h_tokens=0,
    )

    assert status["status"] == "hit"
    assert "缓存命中" in status["message"]


def test_llm_gateway_rate_items_include_cache_columns():
    rates = llm_gateway_rate_items()
    by_model = {item["model"]: item for item in rates["llm_gateway_input"]}

    gpt = by_model["GPT-5.5"]
    assert gpt["rate"] == 5.0
    assert gpt["cached_input_rate"] == 0.5

    claude = by_model["Claude 4.6 Sonnet"]
    assert claude["cache_creation_5m_rate"] == 3.75
    assert claude["cache_creation_1h_rate"] == 6.0


def test_runtime_rate_sync_updates_cost_catalog():
    updated = update_pricing_overrides_from_rates(
        [
            {
                "model": "Runtime Price Model",
                "rate": 2.0,
                "cached_input_rate": 0.2,
                "unit": "1M tokens",
                "price_source": "official_pricing",
            }
        ],
        [
            {
                "model": "Runtime Price Model",
                "rate": 8.0,
                "unit": "1M tokens",
                "price_source": "official_pricing",
            }
        ],
    )

    pricing = get_model_pricing("runtime-price-model")
    cost = calculate_token_cost(
        "runtime-price-model",
        prompt_tokens=1000,
        cached_tokens=500,
        completion_tokens=250,
    )

    assert updated == 1
    assert pricing is not None
    assert pricing.source == "official_pricing"
    assert cost["pricing"]["model"] == "Runtime Price Model"
    assert math.isclose(cost["total_cost"], 0.0031, rel_tol=0, abs_tol=1e-12)
