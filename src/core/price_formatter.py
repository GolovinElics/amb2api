"""
价格格式化工具
用于正确显示不同区域和价格范围的金额
"""


def format_price(rate: float, region: str = None) -> str:
    """
    智能格式化价格，根据价格大小和区域自动选择合适的精度
    
    Args:
        rate: 价格（浮点数）
        region: 区域代码 'US' 或 'EU'（可选）
    
    Returns:
        格式化后的价格字符串
    
    Examples:
        >>> format_price(0.00025, 'EU')
        '$0.000250'
        >>> format_price(0.003, 'EU')
        '$0.00300'
        >>> format_price(0.01, 'US')
        '$0.01000'
        >>> format_price(15.0)
        '$15.00'
    """
    # EU 区域使用更高精度（价格通常较小）
    if region == 'EU':
        if rate < 0.001:
            return f"${rate:.6f}"
        elif rate < 0.01:
            return f"${rate:.5f}"
        elif rate < 1:
            return f"${rate:.3f}"
        else:
            return f"${rate:.2f}"
    
    # US 区域或未指定区域
    if rate < 0.01:
        return f"${rate:.5f}"  # 保险起见，处理可能的小额价格
    elif rate < 1:
        return f"${rate:.3f}"
    else:
        return f"${rate:.2f}"


def format_rate_with_unit(rate: float, unit: str, region: str = None) -> str:
    """
    格式化价格并包含单位
    
    Args:
        rate: 价格
        unit: 单位（如 'hour', '1K tokens', '1M tokens'）
        region: 区域代码
    
    Returns:
        完整的价格字符串
    
    Examples:
        >>> format_rate_with_unit(0.003, '1K tokens', 'EU')
        '$0.00300 / 1K tokens'
        >>> format_rate_with_unit(0.15, 'hour', 'US')
        '$0.150 / hour'
    """
    price_str = format_price(rate, region)
    return f"{price_str} / {unit}"
