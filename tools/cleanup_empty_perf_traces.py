"""
清理 Redis 中空的 perf_traces 键

运行方式: uv run python tools/cleanup_empty_perf_traces.py
"""
import asyncio
import os
import json

async def main():
    # 动态导入避免循环依赖
    from src.storage.storage_adapter import get_storage_adapter
    from log import log
    
    adapter = await get_storage_adapter()
    backend_type = adapter.get_backend_type()
    
    print(f"存储后端: {backend_type}")
    
    if backend_type != "redis":
        print("当前不是 Redis 存储，无需清理")
        return
    
    # 获取所有配置
    all_config = await adapter.get_all_config()
    
    # 找出空的 perf_traces 键
    empty_keys = []
    non_empty_keys = []
    
    for key, value in all_config.items():
        if key.startswith("perf_traces_"):
            if value is None or (isinstance(value, list) and len(value) == 0):
                empty_keys.append(key)
            else:
                count = len(value) if isinstance(value, list) else 1
                non_empty_keys.append((key, count))
    
    print(f"\n找到 {len(empty_keys)} 个空的 perf_traces 键")
    print(f"找到 {len(non_empty_keys)} 个有数据的 perf_traces 键:")
    for key, count in non_empty_keys:
        print(f"  - {key}: {count} 条记录")
    
    if not empty_keys:
        print("\n没有需要清理的空键")
        return
    
    print(f"\n将删除以下空键: {empty_keys[:10]}{'...' if len(empty_keys) > 10 else ''}")
    
    confirm = input("确认删除? (y/N): ")
    if confirm.lower() != 'y':
        print("取消")
        return
    
    # 删除空键
    deleted = 0
    for key in empty_keys:
        try:
            success = await adapter.delete_config(key)
            if success:
                deleted += 1
                print(f"  删除: {key}")
        except Exception as e:
            print(f"  删除失败 {key}: {e}")
    
    print(f"\n完成! 删除了 {deleted} 个空键")

if __name__ == "__main__":
    asyncio.run(main())
