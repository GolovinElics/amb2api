#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_cost_merge_input_output_unknown():
    from src.api.account_api import _parse_cost_rsc_data
    # 构造包含 chartExportData 的 RSC 片段：输入、输出、未标注方向
    raw = (
        '{"chartExportData":[\n'
        ' {"model":"Claude 3.5 Haiku (Input)","value":1.2},\n'
        ' {"model":"Claude 3.5 Haiku (Output)","value":3.4},\n'
        ' {"model":"Claude 3.5 Haiku","value":0.1},\n'
        ' {"model":"Gemini 2.5 Pro (Input)","value":2.5}\n'
        ' ]}'
    )
    res = _parse_cost_rsc_data({"raw": raw})
    by_model = {item["model"]: item for item in res.get("by_model", [])}
    assert "Claude 3.5 Haiku" in by_model
    claude = by_model["Claude 3.5 Haiku"]
    # 输入+输出+未知合计
    assert abs(claude["input_cost"] - 1.2) < 1e-6
    assert abs(claude["output_cost"] - 3.4) < 1e-6
    assert abs(claude["cost"] - (1.2 + 3.4 + 0.1)) < 1e-6
    # 另一个模型只有输入也应有总额
    assert "Gemini 2.5 Pro" in by_model
    gem = by_model["Gemini 2.5 Pro"]
    assert abs(gem["input_cost"] - 2.5) < 1e-6
    assert abs(gem["cost"] - 2.5) < 1e-6

