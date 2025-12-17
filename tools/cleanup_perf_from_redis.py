"""
直接删除 Redis config hash 中的所有 perf 数据

运行方式: REDIS_URI="你的redis地址" PYTHONPATH=. uv run python tools/cleanup_perf_from_redis.py
"""
import asyncio
import os


async def main():
    redis_uri = os.getenv("REDIS_URI")
    if not redis_uri:
        print("错误: 请设置 REDIS_URI 环境变量")
        print("例如: REDIS_URI='redis://localhost:6379' PYTHONPATH=. uv run python tools/cleanup_perf_from_redis.py")
        return
    
    print(f"Redis URI: {redis_uri[:30]}...")
    
    import redis.asyncio as redis_lib
    
    # 连接 Redis
    if redis_uri.startswith("rediss://"):
        client = redis_lib.from_url(redis_uri, decode_responses=True, ssl_cert_reqs=None)
    else:
        client = redis_lib.from_url(redis_uri, decode_responses=True)
    
    await client.ping()
    print("Redis 连接成功")
    
    prefix = os.getenv("REDIS_PREFIX", "AMB2API").strip(":")
    config_hash = f"{prefix}:config"
    
    print(f"Config hash: {config_hash}")
    
    # 获取所有 config 键
    all_keys = await client.hkeys(config_hash)
    print(f"Config hash 中共有 {len(all_keys)} 个键")
    
    # 找出 perf 相关的键
    perf_keys = [k for k in all_keys if k.startswith("perf_traces_") or k == "perf_meta"]
    print(f"找到 {len(perf_keys)} 个 perf 相关键")
    
    if not perf_keys:
        print("没有需要删除的 perf 键")
        await client.close()
        return
    
    # 显示将要删除的键
    for key in sorted(perf_keys):
        val = await client.hget(config_hash, key)
        if val:
            import json
            try:
                data = json.loads(val)
                if isinstance(data, list):
                    print(f"  - {key}: {len(data)} 条记录")
                else:
                    print(f"  - {key}: {type(data).__name__}")
            except:
                print(f"  - {key}: {len(val)} bytes")
        else:
            print(f"  - {key}: 空值")
    
    confirm = input("\n确认删除这些键? (y/N): ")
    if confirm.lower() != 'y':
        print("取消")
        await client.close()
        return
    
    # 删除键
    deleted = await client.hdel(config_hash, *perf_keys)
    print(f"\n完成! 删除了 {deleted} 个键")
    
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
