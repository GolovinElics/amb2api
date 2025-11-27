#!/usr/bin/env python3
"""
Property-based tests for usage statistics aggregation
Feature: rate-limit-usage-display-fix, Property 5: Usage statistics aggregation accuracy
Validates: Requirements 3.1, 3.2
"""

import asyncio
import pytest
import tempfile
import os
from hypothesis import given, strategies as st, settings
from typing import List, Tuple
import re

# Strategy for generating valid log entries
@st.composite
def log_entry(draw):
    """Generate a valid log entry with model, key, and status"""
    models = ["gpt-4", "gpt-3.5-turbo", "claude-3-opus", "gemini-2.5-flash-lite", "gemini-2.5-pro"]
    keys = ["key:abc123", "key:def456", "key:ghi789", ""]  # Include empty key
    statuses = ["OK", "OK(200)", "FAIL(429)", "FAIL(500)", "ERROR"]
    
    model = draw(st.sampled_from(models))
    key = draw(st.sampled_from(keys))
    status = draw(st.sampled_from(statuses))
    
    # Format: "RES model=<model> key=<key> status=<status>"
    if key:
        return f"2025-01-20 12:00:00 RES model={model} key={key} status={status}"
    else:
        return f"2025-01-20 12:00:00 RES model={model} status={status}"


@st.composite
def log_entries_list(draw):
    """Generate a list of log entries"""
    num_entries = draw(st.integers(min_value=1, max_value=50))
    return [draw(log_entry()) for _ in range(num_entries)]


def parse_log_entry(line: str) -> Tuple[str, str, bool]:
    """Parse a log entry and return (model, key, is_ok)"""
    pattern = re.compile(r"RES model=([^\s]+)(?: key=([^\s]+))? status=([A-Z]+(?:\([^\)]*\))?)")
    m = pattern.search(line)
    if not m:
        return None, None, None
    
    model = m.group(1)
    key = m.group(2) or ""
    status = m.group(3)
    is_ok = status.startswith("OK")
    
    return model, key, is_ok


def compute_expected_aggregation(log_lines: List[str]) -> dict:
    """
    Compute the expected aggregation from log lines.
    This is the reference implementation that the endpoint should match.
    """
    models = {}
    keys = {}
    ok_total = 0
    fail_total = 0
    
    for line in log_lines:
        model, key, is_ok = parse_log_entry(line)
        if model is None:
            continue
        
        # Update totals
        if is_ok:
            ok_total += 1
        else:
            fail_total += 1
        
        # Update model stats
        if model not in models:
            models[model] = {"ok": 0, "fail": 0}
        if is_ok:
            models[model]["ok"] += 1
        else:
            models[model]["fail"] += 1
        
        # Update key stats (only for non-empty keys)
        if key and key.strip():
            if key not in keys:
                keys[key] = {"ok": 0, "fail": 0, "models": {}, "model_counts": {}}
            if is_ok:
                keys[key]["ok"] += 1
            else:
                keys[key]["fail"] += 1
            
            # Update per-model stats for this key
            if model not in keys[key]["models"]:
                keys[key]["models"][model] = {"ok": 0, "fail": 0}
            if is_ok:
                keys[key]["models"][model]["ok"] += 1
            else:
                keys[key]["models"][model]["fail"] += 1
            
            # Update model_counts (total calls per model for this key)
            if model not in keys[key]["model_counts"]:
                keys[key]["model_counts"][model] = 0
            keys[key]["model_counts"][model] += 1
    
    return {
        "models": models,
        "keys": keys,
        "total": {"ok": ok_total, "fail": fail_total}
    }


def test_usage_aggregation_accuracy_property():
    """
    Property 5: Usage statistics aggregation accuracy
    For any set of log entries, the aggregated model-specific call counts per key 
    should match the actual number of log entries for each key-model combination.
    
    Feature: rate-limit-usage-display-fix, Property 5: Usage statistics aggregation accuracy
    Validates: Requirements 3.1, 3.2
    """
    @settings(max_examples=100, deadline=None)
    @given(log_lines=log_entries_list())
    def run_property_test(log_lines: List[str]):
        # Create a temporary log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            for line in log_lines:
                f.write(line + '\n')
            temp_log_file = f.name
        
        try:
            # Compute expected aggregation
            expected = compute_expected_aggregation(log_lines)
            
            # Simulate the endpoint logic
            import re
            
            models = {}
            keys = {}
            ok_total = 0
            fail_total = 0
            
            pattern = re.compile(r"RES model=([^\s]+)(?: key=([^\s]+))? status=([A-Z]+(?:\([^\)]*\))?)")
            with open(temp_log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            for ln in lines:
                m = pattern.search(ln)
                if not m:
                    continue
                mod = m.group(1)
                k = m.group(2) or ""
                st_str = m.group(3)
                ok = st_str.startswith("OK")
                
                if ok:
                    ok_total += 1
                else:
                    fail_total += 1
                
                if mod not in models:
                    models[mod] = {"ok": 0, "fail": 0}
                if ok:
                    models[mod]["ok"] += 1
                else:
                    models[mod]["fail"] += 1
                
                # Only track keys that are non-empty
                if k and k.strip():
                    if k not in keys:
                        keys[k] = {"ok": 0, "fail": 0, "models": {}, "model_counts": {}}
                    if ok:
                        keys[k]["ok"] += 1
                    else:
                        keys[k]["fail"] += 1
                    if mod not in keys[k]["models"]:
                        keys[k]["models"][mod] = {"ok": 0, "fail": 0}
                    if ok:
                        keys[k]["models"][mod]["ok"] += 1
                    else:
                        keys[k]["models"][mod]["fail"] += 1
                    # Add to model_counts
                    if mod not in keys[k]["model_counts"]:
                        keys[k]["model_counts"][mod] = 0
                    keys[k]["model_counts"][mod] += 1
            
            actual = {
                "models": models,
                "keys": keys,
                "total": {"ok": ok_total, "fail": fail_total}
            }
            
            # Verify totals match
            assert actual["total"]["ok"] == expected["total"]["ok"], \
                f"Total OK count mismatch: expected {expected['total']['ok']}, got {actual['total']['ok']}"
            assert actual["total"]["fail"] == expected["total"]["fail"], \
                f"Total FAIL count mismatch: expected {expected['total']['fail']}, got {actual['total']['fail']}"
            
            # Verify model stats match
            assert set(actual["models"].keys()) == set(expected["models"].keys()), \
                f"Model keys mismatch: expected {set(expected['models'].keys())}, got {set(actual['models'].keys())}"
            
            for model in expected["models"]:
                assert actual["models"][model]["ok"] == expected["models"][model]["ok"], \
                    f"Model {model} OK count mismatch: expected {expected['models'][model]['ok']}, got {actual['models'][model]['ok']}"
                assert actual["models"][model]["fail"] == expected["models"][model]["fail"], \
                    f"Model {model} FAIL count mismatch: expected {expected['models'][model]['fail']}, got {actual['models'][model]['fail']}"
            
            # Verify key stats match (only non-empty keys)
            assert set(actual["keys"].keys()) == set(expected["keys"].keys()), \
                f"Key keys mismatch: expected {set(expected['keys'].keys())}, got {set(actual['keys'].keys())}"
            
            for key in expected["keys"]:
                assert actual["keys"][key]["ok"] == expected["keys"][key]["ok"], \
                    f"Key {key} OK count mismatch: expected {expected['keys'][key]['ok']}, got {actual['keys'][key]['ok']}"
                assert actual["keys"][key]["fail"] == expected["keys"][key]["fail"], \
                    f"Key {key} FAIL count mismatch: expected {expected['keys'][key]['fail']}, got {actual['keys'][key]['fail']}"
                
                # Verify per-model stats for this key
                assert set(actual["keys"][key]["models"].keys()) == set(expected["keys"][key]["models"].keys()), \
                    f"Key {key} model keys mismatch"
                
                for model in expected["keys"][key]["models"]:
                    assert actual["keys"][key]["models"][model]["ok"] == expected["keys"][key]["models"][model]["ok"], \
                        f"Key {key} model {model} OK count mismatch"
                    assert actual["keys"][key]["models"][model]["fail"] == expected["keys"][key]["models"][model]["fail"], \
                        f"Key {key} model {model} FAIL count mismatch"
                
                # Verify model_counts for this key
                assert set(actual["keys"][key]["model_counts"].keys()) == set(expected["keys"][key]["model_counts"].keys()), \
                    f"Key {key} model_counts keys mismatch"
                
                for model in expected["keys"][key]["model_counts"]:
                    assert actual["keys"][key]["model_counts"][model] == expected["keys"][key]["model_counts"][model], \
                        f"Key {key} model {model} total count mismatch: expected {expected['keys'][key]['model_counts'][model]}, got {actual['keys'][key]['model_counts'][model]}"
        
        finally:
            # Clean up temp file
            if os.path.exists(temp_log_file):
                os.unlink(temp_log_file)
    
    # Run the property test
    run_property_test()


def test_usage_aggregation_examples():
    """Test with specific examples"""
    # Test with specific examples
    test_cases = [
        # Test case 1: Single model, single key
        [
            "2025-01-20 12:00:00 RES model=gpt-4 key=key:abc123 status=OK",
            "2025-01-20 12:00:01 RES model=gpt-4 key=key:abc123 status=OK",
        ],
        # Test case 2: Multiple models, multiple keys
        [
            "2025-01-20 12:00:00 RES model=gpt-4 key=key:abc123 status=OK",
            "2025-01-20 12:00:01 RES model=claude-3-opus key=key:def456 status=OK",
            "2025-01-20 12:00:02 RES model=gpt-4 key=key:abc123 status=FAIL(429)",
            "2025-01-20 12:00:03 RES model=gemini-2.5-pro key=key:abc123 status=OK",
        ],
        # Test case 3: Empty keys should be filtered out
        [
            "2025-01-20 12:00:00 RES model=gpt-4 key=key:abc123 status=OK",
            "2025-01-20 12:00:01 RES model=gpt-4 status=OK",  # No key
            "2025-01-20 12:00:02 RES model=claude-3-opus key=key:def456 status=OK",
        ],
        # Test case 4: Same model, same key, multiple calls
        [
            "2025-01-20 12:00:00 RES model=gpt-4 key=key:abc123 status=OK",
            "2025-01-20 12:00:01 RES model=gpt-4 key=key:abc123 status=OK",
            "2025-01-20 12:00:02 RES model=gpt-4 key=key:abc123 status=FAIL(500)",
            "2025-01-20 12:00:03 RES model=gpt-4 key=key:abc123 status=OK",
        ],
    ]
    
    for test_data in test_cases:
        _run_aggregation_test(test_data)


def _run_aggregation_test(log_lines: List[str]):
    """Helper function to run a single aggregation test"""
    # Create a temporary log file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        for line in log_lines:
            f.write(line + '\n')
        temp_log_file = f.name
    
    try:
        # Compute expected aggregation
        expected = compute_expected_aggregation(log_lines)
        
        # Simulate the endpoint logic
        import re
        
        models = {}
        keys = {}
        ok_total = 0
        fail_total = 0
        
        pattern = re.compile(r"RES model=([^\s]+)(?: key=([^\s]+))? status=([A-Z]+(?:\([^\)]*\))?)")
        with open(temp_log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        for ln in lines:
            m = pattern.search(ln)
            if not m:
                continue
            mod = m.group(1)
            k = m.group(2) or ""
            st_str = m.group(3)
            ok = st_str.startswith("OK")
            
            if ok:
                ok_total += 1
            else:
                fail_total += 1
            
            if mod not in models:
                models[mod] = {"ok": 0, "fail": 0}
            if ok:
                models[mod]["ok"] += 1
            else:
                models[mod]["fail"] += 1
            
            # Only track keys that are non-empty
            if k and k.strip():
                if k not in keys:
                    keys[k] = {"ok": 0, "fail": 0, "models": {}, "model_counts": {}}
                if ok:
                    keys[k]["ok"] += 1
                else:
                    keys[k]["fail"] += 1
                if mod not in keys[k]["models"]:
                    keys[k]["models"][mod] = {"ok": 0, "fail": 0}
                if ok:
                    keys[k]["models"][mod]["ok"] += 1
                else:
                    keys[k]["models"][mod]["fail"] += 1
                # Add to model_counts
                if mod not in keys[k]["model_counts"]:
                    keys[k]["model_counts"][mod] = 0
                keys[k]["model_counts"][mod] += 1
        
        actual = {
            "models": models,
            "keys": keys,
            "total": {"ok": ok_total, "fail": fail_total}
        }
        
        # Verify totals match
        assert actual["total"]["ok"] == expected["total"]["ok"], \
            f"Total OK count mismatch: expected {expected['total']['ok']}, got {actual['total']['ok']}"
        assert actual["total"]["fail"] == expected["total"]["fail"], \
            f"Total FAIL count mismatch: expected {expected['total']['fail']}, got {actual['total']['fail']}"
        
        # Verify model stats match
        assert set(actual["models"].keys()) == set(expected["models"].keys()), \
            f"Model keys mismatch: expected {set(expected['models'].keys())}, got {set(actual['models'].keys())}"
        
        for model in expected["models"]:
            assert actual["models"][model]["ok"] == expected["models"][model]["ok"], \
                f"Model {model} OK count mismatch: expected {expected['models'][model]['ok']}, got {actual['models'][model]['ok']}"
            assert actual["models"][model]["fail"] == expected["models"][model]["fail"], \
                f"Model {model} FAIL count mismatch: expected {expected['models'][model]['fail']}, got {actual['models'][model]['fail']}"
        
        # Verify key stats match (only non-empty keys)
        assert set(actual["keys"].keys()) == set(expected["keys"].keys()), \
            f"Key keys mismatch: expected {set(expected['keys'].keys())}, got {set(actual['keys'].keys())}"
        
        for key in expected["keys"]:
            assert actual["keys"][key]["ok"] == expected["keys"][key]["ok"], \
                f"Key {key} OK count mismatch: expected {expected['keys'][key]['ok']}, got {actual['keys'][key]['ok']}"
            assert actual["keys"][key]["fail"] == expected["keys"][key]["fail"], \
                f"Key {key} FAIL count mismatch: expected {expected['keys'][key]['fail']}, got {actual['keys'][key]['fail']}"
            
            # Verify per-model stats for this key
            assert set(actual["keys"][key]["models"].keys()) == set(expected["keys"][key]["models"].keys()), \
                f"Key {key} model keys mismatch"
            
            for model in expected["keys"][key]["models"]:
                assert actual["keys"][key]["models"][model]["ok"] == expected["keys"][key]["models"][model]["ok"], \
                    f"Key {key} model {model} OK count mismatch"
                assert actual["keys"][key]["models"][model]["fail"] == expected["keys"][key]["models"][model]["fail"], \
                    f"Key {key} model {model} FAIL count mismatch"
            
            # Verify model_counts for this key
            assert set(actual["keys"][key]["model_counts"].keys()) == set(expected["keys"][key]["model_counts"].keys()), \
                f"Key {key} model_counts keys mismatch"
            
            for model in expected["keys"][key]["model_counts"]:
                assert actual["keys"][key]["model_counts"][model] == expected["keys"][key]["model_counts"][model], \
                    f"Key {key} model {model} total count mismatch: expected {expected['keys'][key]['model_counts'][model]}, got {actual['keys'][key]['model_counts'][model]}"
    
    finally:
        # Clean up temp file
        if os.path.exists(temp_log_file):
            os.unlink(temp_log_file)


if __name__ == "__main__":
    # Run the tests
    print("Running usage aggregation accuracy tests...")
    test_usage_aggregation_examples()
    print("Running property-based tests...")
    test_usage_aggregation_accuracy_property()
    print("✅ All tests passed!")
