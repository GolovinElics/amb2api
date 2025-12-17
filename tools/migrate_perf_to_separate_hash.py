"""
迁移性能追踪数据从 config hash 到独立的 perf hash

运行方式: PYTHONPATH=. uv run python tools/migrate_perf_to_separate_hash.py

此脚本会:
1. 从 config hash 读取所有 perf_traces_* 和 perf_meta 键
2. 将它们写入新的 perf hash
3. 从 config hash 删除这些键
"""
import asyncio
import os


async def main():
    from src.storage.storage_adapter import get_storage_adapter
    from log import log
    
    adapter = await get_storage_adapter()
    backend_type = adapter.get_backend_type()
    
    print(f"存储后端: {backend_type}")
    
    if backend_type != "redis":
        print("当前不是 Redis 存储，无需迁移")
        return
    
    # 获取底层 backend
    backend = adapter._backend
    
    # 读取 config hash 中的所有数据
    all_config = await adapter.get_all_config()
    
    # 找出 perf 相关的键
    perf_keys = {}
    for key, value in all_config.items():
        if key.startswith("perf_traces_") or key == "perf_meta":
            perf_keys[key] = value
    
    print(f"\n在 config hash 中找到 {len(perf_keys)} 个 perf 相关键:")
    for key, value in perf_keys.items():
        if isinstance(value, list):
            print(f"  - {key}: {len(value)} 条记录")
        else:
            print(f"  - {key}: {type(value).__name__}")
    
    if not perf_keys:
        print("\n没有需要迁移的 perf 数据")
        return
    
    # 确认迁移
    print(f"\n将把这些数据迁移到独立的 perf hash，并从 config hash 删除")
    confirm = input("确认迁移? (y/N): ")
    if confirm.lower() != 'y':
        print("取消")
        return
    
    # 迁移数据到 perf hash
    migrated = 0
    for key, value in perf_keys.items():
        # 跳过空值
        if value is None or (isinstance(value, list) and len(value) == 0):
            print(f"  跳过空键: {key}")
            # 仍然从 config 删除空键
            await adapter._backend.delete_config(key)
            print(f"  删除空键: {key}")
            continue
        
        # 写入 perf hash
        success = await adapter.set_perf(key, value)
        if success:
            # 从 config hash 删除
            await adapter._backend.delete_config(key)
            print(f"  迁移: {key}")
            migrated += 1
        else:
            print(f"  迁移失败: {key}")
    
    print(f"\n完成! 迁移了 {migrated} 个键到独立的 perf hash")
    print("请重启服务器使更改生效")

if __name__ == "__main__":
    asyncio.run(main())
