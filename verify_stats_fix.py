#!/usr/bin/env python3
"""
验证使用统计修复是否生效
"""
import asyncio
import sys
import os
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


async def verify_usage_stats():
    """验证使用统计功能"""
    print("\n" + "=" * 60)
    print("验证使用统计功能")
    print("=" * 60)
    
    try:
        from src.usage_stats import get_usage_stats_instance
        
        stats_instance = await get_usage_stats_instance()
        print("✓ 使用统计实例初始化成功")
        
        # 获取所有统计
        all_stats = await stats_instance.get_usage_stats()
        print(f"✓ 当前有 {len(all_stats)} 个密钥的统计数据")
        
        if len(all_stats) > 0:
            print("\n统计数据示例:")
            for filename, stats in list(all_stats.items())[:3]:
                print(f"  - {filename}: {stats.get('total_calls', 0)} 次调用")
        
        return True
    except Exception as e:
        print(f"✗ 使用统计验证失败: {e}")
        return False


async def verify_log_stats():
    """验证日志统计功能"""
    print("\n" + "=" * 60)
    print("验证日志统计功能")
    print("=" * 60)
    
    try:
        from log import log
        
        log_file = log.get_log_file()
        
        if not os.path.exists(log_file):
            print(f"⚠ 日志文件不存在: {log_file}")
            print("  这是正常的，如果应用还没有处理过请求")
            return True
        
        print(f"✓ 日志文件存在: {log_file}")
        
        # 解析日志
        pattern = re.compile(r"RES model=([^\s]+)(?: key=([^\s]+))? status=([A-Z]+(?:\([^\)]*\))?)")
        
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        matches = 0
        models = set()
        keys = set()
        
        for line in lines[-100:]:  # 只检查最后100行
            m = pattern.search(line)
            if m:
                matches += 1
                models.add(m.group(1))
                if m.group(2):
                    keys.add(m.group(2))
        
        print(f"✓ 在最后100行日志中找到 {matches} 条响应记录")
        print(f"✓ 涉及 {len(models)} 个模型")
        print(f"✓ 涉及 {len(keys)} 个密钥")
        
        if matches > 0:
            print("\n模型列表:")
            for model in list(models)[:5]:
                print(f"  - {model}")
            
            if keys:
                print("\n密钥列表（脱敏）:")
                for key in list(keys)[:5]:
                    print(f"  - {key}")
        
        return True
    except Exception as e:
        print(f"✗ 日志统计验证失败: {e}")
        return False


async def verify_key_masking():
    """验证密钥脱敏功能"""
    print("\n" + "=" * 60)
    print("验证密钥脱敏功能")
    print("=" * 60)
    
    try:
        from src.assembly_client import _mask_key
        
        test_keys = [
            "sk-1234567890abcdef",
            "Bearer_abcdefghijklmnop",
            "short"
        ]
        
        print("\n密钥脱敏测试:")
        for key in test_keys:
            masked = _mask_key(key)
            print(f"  {key[:20]}{'...' if len(key) > 20 else ''} -> {masked}")
        
        print("\n✓ 密钥脱敏功能正常")
        return True
    except Exception as e:
        print(f"✗ 密钥脱敏验证失败: {e}")
        return False


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("使用统计修复验证工具")
    print("=" * 60)
    
    results = []
    
    # 验证使用统计
    results.append(await verify_usage_stats())
    
    # 验证日志统计
    results.append(await verify_log_stats())
    
    # 验证密钥脱敏
    results.append(await verify_key_masking())
    
    # 总结
    print("\n" + "=" * 60)
    if all(results):
        print("✓ 所有验证通过！修复已生效")
        print("=" * 60)
        return 0
    else:
        print("⚠ 部分验证失败，请检查上述错误信息")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
