#!/usr/bin/env python3
"""
统计数据迁移脚本

将旧的统计数据（从日志文件）迁移到新的统一统计系统
"""
import asyncio
import os
import re
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from log import log


async def migrate_stats():
    """迁移统计数据"""
    from src.unified_stats import get_unified_stats, mask_key
    from src.storage_adapter import get_storage_adapter
    
    print("开始迁移统计数据...")
    
    # 获取配置的密钥列表
    adapter = await get_storage_adapter()
    cfg_keys = await adapter.get_config("assembly_api_keys", [])
    if isinstance(cfg_keys, str):
        cfg_keys = [x.strip() for x in cfg_keys.replace("\n", ",").split(",") if x.strip()]
    
    print(f"找到 {len(cfg_keys)} 个配置的密钥")
    
    # 构建脱敏密钥到完整密钥的映射
    masked_to_full = {mask_key(k): k for k in cfg_keys}
    
    # 从日志文件读取统计数据
    log_file = log.get_log_file()
    if not os.path.exists(log_file):
        print(f"日志文件不存在: {log_file}")
        return
    
    print(f"从日志文件读取统计数据: {log_file}")
    
    # 解析日志
    pattern = re.compile(r"RES model=([^\s]+)(?: key=([^\s]+))? status=([A-Z]+(?:\([^\)]*\))?)")
    stats = {}  # masked_key -> {model -> {ok, fail}}
    
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if not m:
                continue
            
            model = m.group(1)
            masked_key = m.group(2) or ""
            status = m.group(3)
            
            if not masked_key or not masked_key.strip():
                continue
            
            # 只处理有效密钥
            if masked_key not in masked_to_full:
                continue
            
            if masked_key not in stats:
                stats[masked_key] = {}
            
            if model not in stats[masked_key]:
                stats[masked_key][model] = {"ok": 0, "fail": 0}
            
            if status.startswith("OK"):
                stats[masked_key][model]["ok"] += 1
            else:
                stats[masked_key][model]["fail"] += 1
    
    print(f"从日志中解析出 {len(stats)} 个密钥的统计数据")
    
    # 迁移到统一统计
    unified_stats = await get_unified_stats()
    
    for masked_key, model_stats in stats.items():
        full_key = masked_to_full.get(masked_key)
        if not full_key:
            continue
        
        for model, counts in model_stats.items():
            # 记录成功调用
            for _ in range(counts["ok"]):
                await unified_stats.record_call(full_key, model, success=True)
            
            # 记录失败调用
            for _ in range(counts["fail"]):
                await unified_stats.record_call(full_key, model, success=False)
        
        print(f"  迁移密钥 {masked_key}: {sum(c['ok'] + c['fail'] for c in model_stats.values())} 次调用")
    
    print("迁移完成！")


if __name__ == "__main__":
    asyncio.run(migrate_stats())
