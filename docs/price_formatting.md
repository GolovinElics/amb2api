# 价格格式化指南

## 使用方法

```python
from src.price_formatter import format_price, format_rate_with_unit

# EU 区域价格（通常较小）
eu_price = format_price(0.003, 'EU')  # "$0.00300"

# US 区域价格
us_price = format_price(0.15, 'US')   # "$0.150"

# 包含单位
full_price = format_rate_with_unit(0.003, '1K tokens', 'EU')  # "$0.00300 / 1K tokens"
```

## 为什么需要这个？

不同区域的价格范围差异很大：
- **EU 区域**：最低 $0.00025，需要高精度格式化
- **US 区域**：最低 $0.01，标准精度即可

使用 `{:.2f}` 格式化会导致小额价格显示为 $0.00，这是不正确的。

## 测试

运行测试确保格式化正确：

```bash
python3 -m pytest tests/test_price_formatter.py -v
```
