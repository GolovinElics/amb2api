#!/usr/bin/env python3
"""
正确解析 EU 区域的 LLM Gateway 价格
"""

# EU 区域的实际数据
eu_llm_input = {
    "Claude Sonnet 3.7": {"rate": 0.003, "unit": "1K tokens"},
    "Claude Sonnet 3.5": {"rate": 0.003, "unit": "1K tokens"},
    "Claude 3.0 Haiku": {"rate": 0.00025, "unit": "1K tokens"},
    "Claude 4 Sonnet": {"rate": 0.003, "unit": "1K tokens"},
}

eu_llm_output = {
    "Claude 3.7 Sonnet": {"rate": 0.015, "unit": "1K tokens"},
    "Claude 3.0 Haiku": {"rate": 0.00125, "unit": "1K tokens"},
    "Claude 3.5 Sonnet": {"rate": 0.015, "unit": "1K tokens"},
    "Claude 4 Sonnet": {"rate": 0.015, "unit": "1K tokens"},
}

print("="*80)
print("EU 区域 - LLM Gateway + LeMUR 价格")
print("="*80)

print("\n📥 输入 Token 价格")
print("-"*80)
print(f"{'模型':<30} {'价格':<20} {'单位':<15}")
print("-"*80)
for model, info in eu_llm_input.items():
    # 使用 5 位小数精度显示
    print(f"{model:<30} ${info['rate']:<19.5f} {info['unit']:<15}")

print("\n📤 输出 Token 价格")
print("-"*80)
print(f"{'模型':<30} {'价格':<20} {'单位':<15}")
print("-"*80)
for model, info in eu_llm_output.items():
    print(f"{model:<30} ${info['rate']:<19.5f} {info['unit']:<15}")

# 创建合并视图（正确的方式）
print("\n" + "="*80)
print("合并视图 - 输入/输出对比")
print("="*80)
print(f"{'模型':<30} {'输入价格':<20} {'输出价格':<20} {'倍数':<10}")
print("-"*80)

# 标准化模型名称进行匹配
def normalize_name(name):
    """标准化模型名称以便匹配"""
    # 移除多余空格，统一大小写
    name = name.strip().lower()
    # 统一命名格式
    name = name.replace("claude sonnet", "claude_sonnet")
    name = name.replace("claude haiku", "claude_haiku")
    return name

# 创建标准化的映射
input_normalized = {normalize_name(k): (k, v) for k, v in eu_llm_input.items()}
output_normalized = {normalize_name(k): (k, v) for k, v in eu_llm_output.items()}

# 找到所有唯一的模型
all_models = set(input_normalized.keys()) | set(output_normalized.keys())

for norm_name in sorted(all_models):
    input_data = input_normalized.get(norm_name)
    output_data = output_normalized.get(norm_name)
    
    if input_data and output_data:
        input_name, input_info = input_data
        output_name, output_info = output_data
        
        input_rate = input_info['rate']
        output_rate = output_info['rate']
        ratio = output_rate / input_rate if input_rate > 0 else 0
        
        # 使用原始名称（取输入或输出中较规范的）
        display_name = output_name if "3.7" in output_name or "3.5" in output_name else input_name
        
        print(f"{display_name:<30} ${input_rate:<19.5f} ${output_rate:<19.5f} {ratio:<10.1f}x")
    elif input_data:
        input_name, input_info = input_data
        print(f"{input_name:<30} ${input_info['rate']:<19.5f} {'N/A':<20} {'N/A':<10}")
    elif output_data:
        output_name, output_info = output_data
        print(f"{output_name:<30} {'N/A':<20} ${output_info['rate']:<19.5f} {'N/A':<10}")

print("\n" + "="*80)
print("⚠️  常见错误及解决方案")
print("="*80)
print("""
1. 精度丢失问题：
   ❌ 错误：使用 {:.2f} 格式化 0.003 → 显示为 $0.00
   ✅ 正确：使用 {:.5f} 或 {:.6f} 格式化 → 显示为 $0.00300

2. 单位混淆问题：
   ❌ 错误：混合使用 "1K tokens" 和 "1M tokens"
   ✅ 正确：统一单位，或在显示时明确标注
   
3. 模型名称不匹配：
   ❌ 错误："Claude Sonnet 3.7" vs "Claude 3.7 Sonnet"
   ✅ 正确：标准化名称后再匹配

4. 合并逻辑错误：
   ❌ 错误：直接覆盖或相加输入输出价格
   ✅ 正确：分别存储，显示时并列展示

5. 数据类型问题：
   ❌ 错误：将价格存储为字符串 "0.003"
   ✅ 正确：存储为浮点数 0.003
""")

print("\n" + "="*80)
print("💡 推荐的数据结构")
print("="*80)
print("""
{
  "region": "EU",
  "models": [
    {
      "name": "Claude 3.7 Sonnet",
      "input_rate": 0.003,
      "output_rate": 0.015,
      "unit": "1K tokens",
      "ratio": 5.0
    },
    {
      "name": "Claude 3.5 Sonnet",
      "input_rate": 0.003,
      "output_rate": 0.015,
      "unit": "1K tokens",
      "ratio": 5.0
    }
  ]
}
""")

# 生成正确的 JSON 结构
import json

correct_structure = {
    "region": "EU",
    "currency": "USD",
    "llm_gateway_models": []
}

for norm_name in sorted(all_models):
    input_data = input_normalized.get(norm_name)
    output_data = output_normalized.get(norm_name)
    
    if input_data and output_data:
        input_name, input_info = input_data
        output_name, output_info = output_data
        
        model_entry = {
            "name": output_name,
            "input_rate": input_info['rate'],
            "output_rate": output_info['rate'],
            "unit": input_info['unit'],
            "ratio": round(output_info['rate'] / input_info['rate'], 1) if input_info['rate'] > 0 else None
        }
        correct_structure["llm_gateway_models"].append(model_entry)

print("\n" + "="*80)
print("生成的正确 JSON 结构：")
print("="*80)
print(json.dumps(correct_structure, indent=2, ensure_ascii=False))

# 保存到文件
with open('tests/eu_rates_correct.json', 'w', encoding='utf-8') as f:
    json.dump(correct_structure, f, indent=2, ensure_ascii=False)

print("\n✅ 已保存到: tests/eu_rates_correct.json")
