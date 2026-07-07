from pathlib import Path


def test_control_panel_only_exposes_global_fake_streaming_toggle():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert 'id="fakeStreamEnabled"' in html
    assert "启用全局假流式" in html

    assert 'id="enableRealStreaming"' not in html
    assert "启用真实流式" not in html
    assert 'id="streamKeepaliveSeconds"' not in html
    assert 'id="streamBootstrapRetries"' not in html

    assert "enable_real_streaming: true" in html


def test_performance_waterfall_surfaces_stream_and_cache_diagnostics():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert 'id="wfStreamReason"' in html
    assert 'id="wfUpstreamStream"' in html
    assert 'id="wfCacheApplied"' in html
    assert 'id="wfCacheStatus"' in html
    assert 'id="wfCostTotal"' in html
    assert 'id="wfCostInput"' in html
    assert 'id="wfCostCacheRead"' in html
    assert 'id="wfCostOutput"' in html
    assert "metadata.stream_route_reason" in html
    assert "metadata.upstream_stream_requested" in html
    assert "metadata.prompt_cache_gateway_mode" in html
    assert "metadata.cache_prompt_details_present" in html
    assert "trace.cache_status" in html
    assert "trace.cost" in html
    assert "const hasExplicitCacheDirective = cacheControlApplied || cacheKeyApplied;" in html
    assert "cacheEnabled || hasExplicitCacheDirective" in html
    assert "' / helpers off'" in html


def test_account_cost_ui_uses_precise_currency_formatter_for_small_amounts():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert "function formatAccountCurrency" in html
    assert "formatAccountCurrency(totalCost" in html
    assert "formatAccountCurrency(item.cost" in html
    assert "totalEl.textContent = formatAccountCurrency(detailTotal" in html
    assert "formatAccountCurrency(item.amount" in html
    assert "const sign = amount < 0 ? '-' : '';" in html
    assert "sign + '$' + abs.toLocaleString" in html
    assert "sign + '$' + absText" in html


def test_account_rates_table_surfaces_cache_prices():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert "cachedInputDisplay" in html
    assert "cache5mDisplay" in html
    assert "cache1hDisplay" in html
    assert "<th>缓存读取</th>" in html
    assert "<th>缓存写入 5m</th>" in html
    assert "<th>缓存写入 1h</th>" in html


def test_account_pages_cache_usage_cost_and_rates_by_filter_without_bad_query_strings():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert "makeAccountCacheKey" in html
    assert "accountCache.usage[summaryCacheKey]" in html
    assert "accountCache.usage[detailCacheKey]" in html
    assert "accountCache.cost[summaryCacheKey]" in html
    assert "accountCache.cost[detailCacheKey]" in html
    assert "accountCache.rates[region]" in html
    assert "loadAccountUsageAll(false)" in html
    assert "? account_email =" not in html


def test_account_charts_share_coordinate_helpers_and_hide_tooltips_on_scroll():
    html = Path("front/control_panel.html").read_text(encoding="utf-8")

    assert "const ACCOUNT_CHART_X_PADDING = 0.05;" in html
    assert "function getAccountChartPointRatio" in html
    assert "function getAccountChartPointLeft" in html
    assert "function getNearestAccountChartIndex" in html
    assert "function getAccountChartLabelStyle" in html

    assert "getAccountChartPointRatio(i, dataPointCount) * width" in html
    assert "getAccountChartPointRatio(i, arr.length) * width" in html
    assert "getNearestAccountChartIndex(event.clientX, rect, dailyByModel.length)" in html
    assert "getNearestAccountChartIndex(event.clientX, rect, trend.length)" in html
    assert "getAccountChartLabelStyle(idx, dates.length)" in html

    assert 'ontouchend="finishUsageTouch()"' in html
    assert 'ontouchcancel="finishUsageTouch()"' in html
    assert 'ontouchend="finishCostTouch()"' in html
    assert 'ontouchcancel="finishCostTouch()"' in html
    assert "window.addEventListener('scroll', hideAccountChartTooltips" in html
    assert "shouldDismissAccountChartTouch" in html
    assert "dismissed: false" in html
    assert "start.dismissed = true;" in html
    assert "shouldDismissAccountChartTouch(event, 'usage', hideUsageTooltip)" in html
    assert "shouldDismissAccountChartTouch(event, 'cost', hideCostTooltip)" in html
