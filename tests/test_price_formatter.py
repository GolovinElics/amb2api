"""
价格格式化测试
"""
import pytest
from src.price_formatter import format_price, format_rate_with_unit


class TestFormatPrice:
    """测试 format_price 函数"""
    
    def test_eu_very_small_prices(self):
        """测试 EU 区域极小价格（< $0.001）"""
        assert format_price(0.00025, 'EU') == "$0.000250"
        assert format_price(0.0005, 'EU') == "$0.000500"
    
    def test_eu_small_prices(self):
        """测试 EU 区域小额价格（$0.001 - $0.01）"""
        assert format_price(0.003, 'EU') == "$0.00300"
        assert format_price(0.00125, 'EU') == "$0.00125"
    
    def test_eu_medium_prices(self):
        """测试 EU 区域中等价格（$0.01 - $1.00）"""
        assert format_price(0.015, 'EU') == "$0.015"
        assert format_price(0.5, 'EU') == "$0.500"
    
    def test_eu_large_prices(self):
        """测试 EU 区域大额价格（> $1.00）"""
        assert format_price(1.5, 'EU') == "$1.50"
        assert format_price(15.0, 'EU') == "$15.00"
    
    def test_us_small_prices(self):
        """测试 US 区域小额价格（< $0.01）"""
        assert format_price(0.001, 'US') == "$0.00100"
        assert format_price(0.005, 'US') == "$0.00500"
    
    def test_us_medium_prices(self):
        """测试 US 区域中等价格（$0.01 - $1.00）"""
        assert format_price(0.01, 'US') == "$0.01000"
        assert format_price(0.15, 'US') == "$0.150"
        assert format_price(0.47, 'US') == "$0.470"
    
    def test_us_large_prices(self):
        """测试 US 区域大额价格（> $1.00）"""
        assert format_price(1.25, 'US') == "$1.25"
        assert format_price(15.0, 'US') == "$15.00"
        assert format_price(75.0, 'US') == "$75.00"
    
    def test_no_region_specified(self):
        """测试未指定区域（使用默认逻辑）"""
        assert format_price(0.003) == "$0.00300"
        assert format_price(0.15) == "$0.150"
        assert format_price(15.0) == "$15.00"
    
    def test_zero_price(self):
        """测试零价格"""
        assert format_price(0.0, 'US') == "$0.00000"
        assert format_price(0.0, 'EU') == "$0.000000"


class TestFormatRateWithUnit:
    """测试 format_rate_with_unit 函数"""
    
    def test_eu_with_1k_tokens(self):
        """测试 EU 区域 1K tokens 单位"""
        assert format_rate_with_unit(0.003, '1K tokens', 'EU') == "$0.00300 / 1K tokens"
        assert format_rate_with_unit(0.015, '1K tokens', 'EU') == "$0.015 / 1K tokens"
    
    def test_us_with_hour(self):
        """测试 US 区域 hour 单位"""
        assert format_rate_with_unit(0.15, 'hour', 'US') == "$0.150 / hour"
        assert format_rate_with_unit(0.47, 'hour', 'US') == "$0.470 / hour"
    
    def test_us_with_1m_tokens(self):
        """测试 US 区域 1M tokens 单位"""
        assert format_rate_with_unit(1.25, '1M tokens', 'US') == "$1.25 / 1M tokens"
        assert format_rate_with_unit(15.0, '1M tokens', 'US') == "$15.00 / 1M tokens"
    
    def test_no_region(self):
        """测试未指定区域"""
        assert format_rate_with_unit(0.003, '1K tokens') == "$0.00300 / 1K tokens"
        assert format_rate_with_unit(1.25, '1M tokens') == "$1.25 / 1M tokens"


class TestRealWorldScenarios:
    """测试真实场景"""
    
    def test_eu_llm_gateway_prices(self):
        """测试 EU LLM Gateway 实际价格"""
        # Claude 3.0 Haiku
        assert format_price(0.00025, 'EU') == "$0.000250"  # 输入
        assert format_price(0.00125, 'EU') == "$0.00125"   # 输出
        
        # Claude 3.7 Sonnet
        assert format_price(0.003, 'EU') == "$0.00300"     # 输入
        assert format_price(0.015, 'EU') == "$0.015"       # 输出
    
    def test_us_speech_to_text_prices(self):
        """测试 US Speech-to-Text 实际价格"""
        assert format_price(0.27, 'US') == "$0.270"  # Slam-1
        assert format_price(0.15, 'US') == "$0.150"  # Universal
        assert format_price(0.12, 'US') == "$0.120"  # Nano
    
    def test_us_speech_understanding_prices(self):
        """测试 US Speech Understanding 实际价格"""
        assert format_price(0.01, 'US') == "$0.01000"  # Key Phrases
        assert format_price(0.08, 'US') == "$0.08000"  # Auto Chapters
        assert format_price(0.15, 'US') == "$0.150"    # Content Moderation
    
    def test_us_llm_gateway_prices(self):
        """测试 US LLM Gateway 实际价格"""
        # 输入价格
        assert format_price(0.15, 'US') == "$0.150"   # GPT OSS 120b
        assert format_price(1.25, 'US') == "$1.25"    # GPT 5
        assert format_price(15.0, 'US') == "$15.00"   # Claude Opus 4
        
        # 输出价格
        assert format_price(0.60, 'US') == "$0.600"   # GPT OSS 120b
        assert format_price(2.0, 'US') == "$2.00"     # GPT 5 Mini
        assert format_price(75.0, 'US') == "$75.00"   # Claude Opus 4
