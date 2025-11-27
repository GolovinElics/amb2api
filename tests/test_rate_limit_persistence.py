#!/usr/bin/env python3
"""
Property-based tests for rate limit data persistence
Feature: rate-limit-usage-display-fix, Property 1: Rate limit data persistence round-trip
Validates: Requirements 4.1, 4.2, 4.3
"""

import asyncio
import pytest
from hypothesis import given, strategies as st, settings
from typing import Dict, Any
import time

# Import the functions we're testing
from src.assembly_client import _save_rate_limit_info, _load_rate_limit_info, _rate_limit_info, _rate_limit_loaded
from src.storage_adapter import get_storage_adapter


# Strategy for generating valid rate limit info
@st.composite
def rate_limit_entry(draw):
    """Generate a valid rate limit info entry"""
    return {
        "key": draw(st.text(min_size=4, max_size=20, alphabet=st.characters(min_codepoint=97, max_codepoint=122))),
        "full_key": draw(st.text(min_size=32, max_size=64, alphabet=st.characters(min_codepoint=97, max_codepoint=122) | st.characters(min_codepoint=48, max_codepoint=57))),
        "last_request_time": draw(st.floats(min_value=1000000000.0, max_value=2000000000.0)),
        "limit": draw(st.integers(min_value=1, max_value=10000)),
        "remaining": draw(st.integers(min_value=0, max_value=10000)),
        "used": draw(st.integers(min_value=0, max_value=10000)),
        "reset_time": draw(st.floats(min_value=1000000000.0, max_value=2000000000.0)),
    }


@st.composite
def rate_limit_info_dict(draw):
    """Generate a dictionary of rate limit info with integer keys"""
    # Generate 1-5 entries with integer keys
    num_entries = draw(st.integers(min_value=1, max_value=5))
    result = {}
    for i in range(num_entries):
        idx = draw(st.integers(min_value=0, max_value=100))
        result[idx] = draw(rate_limit_entry())
    return result


@pytest.fixture
async def clean_rate_limit_state():
    """Clean up rate limit state before and after tests"""
    # Import the global variables
    import src.assembly_client as ac
    
    # Save original state
    original_info = ac._rate_limit_info.copy()
    original_loaded = ac._rate_limit_loaded
    
    # Reset state
    ac._rate_limit_info = {}
    ac._rate_limit_loaded = False
    
    yield
    
    # Restore original state
    ac._rate_limit_info = original_info
    ac._rate_limit_loaded = original_loaded


@pytest.mark.asyncio
@settings(max_examples=100, deadline=None)
@given(test_data=rate_limit_info_dict())
async def test_rate_limit_round_trip(test_data: Dict[int, Dict[str, Any]]):
    """
    Property 1: Rate limit data persistence round-trip
    For any rate limit information with integer indices, saving to Redis then loading 
    should preserve all data with correct type conversions (integers to strings for 
    storage, strings to integers for loading)
    
    Feature: rate-limit-usage-display-fix, Property 1: Rate limit data persistence round-trip
    Validates: Requirements 4.1, 4.2, 4.3
    """
    import src.assembly_client as ac
    
    # Reset state
    ac._rate_limit_info = {}
    ac._rate_limit_loaded = False
    
    # Set the test data
    ac._rate_limit_info = test_data.copy()
    
    # Save to storage
    await _save_rate_limit_info()
    
    # Clear in-memory data
    ac._rate_limit_info = {}
    ac._rate_limit_loaded = False
    
    # Load from storage
    await _load_rate_limit_info()
    
    # Verify the data matches
    loaded_data = ac._rate_limit_info
    
    # Check that all keys are present and are integers
    assert len(loaded_data) == len(test_data), f"Expected {len(test_data)} keys, got {len(loaded_data)}"
    
    for idx, expected_info in test_data.items():
        assert idx in loaded_data, f"Key {idx} not found in loaded data"
        assert isinstance(idx, int), f"Key {idx} should be an integer"
        
        loaded_info = loaded_data[idx]
        
        # Verify all fields match
        for field in ["key", "full_key", "last_request_time", "limit", "remaining", "used", "reset_time"]:
            assert field in loaded_info, f"Field {field} missing in loaded data for key {idx}"
            assert loaded_info[field] == expected_info[field], \
                f"Field {field} mismatch for key {idx}: expected {expected_info[field]}, got {loaded_info[field]}"


def test_rate_limit_round_trip_sync():
    """Synchronous wrapper for the async property test"""
    # This is a workaround since hypothesis doesn't directly support async tests
    # We'll run a few examples manually
    
    test_cases = [
        # Test case 1: Single entry
        {0: {
            "key": "test",
            "full_key": "test1234567890abcdef1234567890ab",
            "last_request_time": 1700000000.0,
            "limit": 100,
            "remaining": 50,
            "used": 50,
            "reset_time": 1700000060.0,
        }},
        # Test case 2: Multiple entries
        {
            0: {
                "key": "key0",
                "full_key": "key0123456789abcdef0123456789ab",
                "last_request_time": 1700000000.0,
                "limit": 100,
                "remaining": 80,
                "used": 20,
                "reset_time": 1700000060.0,
            },
            1: {
                "key": "key1",
                "full_key": "key1123456789abcdef0123456789ab",
                "last_request_time": 1700000010.0,
                "limit": 200,
                "remaining": 150,
                "used": 50,
                "reset_time": 1700000070.0,
            },
        },
        # Test case 3: Non-sequential indices
        {
            5: {
                "key": "key5",
                "full_key": "key5123456789abcdef0123456789ab",
                "last_request_time": 1700000000.0,
                "limit": 50,
                "remaining": 25,
                "used": 25,
                "reset_time": 1700000060.0,
            },
            10: {
                "key": "key10",
                "full_key": "key10123456789abcdef0123456789a",
                "last_request_time": 1700000020.0,
                "limit": 300,
                "remaining": 200,
                "used": 100,
                "reset_time": 1700000080.0,
            },
        },
    ]
    
    for test_data in test_cases:
        asyncio.run(_run_round_trip_test(test_data))


async def _run_round_trip_test(test_data: Dict[int, Dict[str, Any]]):
    """Helper function to run a single round-trip test"""
    import src.assembly_client as ac
    
    # Reset state
    ac._rate_limit_info = {}
    ac._rate_limit_loaded = False
    
    # Set the test data
    ac._rate_limit_info = test_data.copy()
    
    # Save to storage
    await _save_rate_limit_info()
    
    # Clear in-memory data
    ac._rate_limit_info = {}
    ac._rate_limit_loaded = False
    
    # Load from storage
    await _load_rate_limit_info()
    
    # Verify the data matches
    loaded_data = ac._rate_limit_info
    
    # Check that all keys are present and are integers
    assert len(loaded_data) == len(test_data), f"Expected {len(test_data)} keys, got {len(loaded_data)}"
    
    for idx, expected_info in test_data.items():
        assert idx in loaded_data, f"Key {idx} not found in loaded data"
        assert isinstance(idx, int), f"Key {idx} should be an integer"
        
        loaded_info = loaded_data[idx]
        
        # Verify all fields match
        for field in ["key", "full_key", "last_request_time", "limit", "remaining", "used", "reset_time"]:
            assert field in loaded_info, f"Field {field} missing in loaded data for key {idx}"
            assert loaded_info[field] == expected_info[field], \
                f"Field {field} mismatch for key {idx}: expected {expected_info[field]}, got {loaded_info[field]}"


if __name__ == "__main__":
    # Run the synchronous test
    print("Running rate limit persistence round-trip tests...")
    test_rate_limit_round_trip_sync()
    print("✅ All tests passed!")
