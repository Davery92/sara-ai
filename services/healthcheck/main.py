import asyncio, os, aioredis, asyncpg, httpx

async def ping():
    redis = aioredis.from_url("redis://redis:6379")
    pg = await asyncpg.connect(
        user=os.getenv("POSTGRES_USER"), 
        password=os.getenv("POSTGRES_PASSWORD"), 
        database=os.getenv("POSTGRES_DB"), 
        host="postgres"
    )
    async with httpx.AsyncClient() as client:
        _ = await client.get("http://minio:9000/minio/health/ready")
        _ = await client.get("http://temporal:7233/health")

    await redis.ping()
    await pg.fetchval("SELECT 1")
    print("✅ all good")

if __name__ == "__main__":
    asyncio.run(ping())
