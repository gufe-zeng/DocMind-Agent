from redis.asyncio import Redis


async def check_redis(url: str) -> None:
    client = Redis.from_url(
        url,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )
    try:
        ok = await client.ping()
        if not ok:
            raise RuntimeError("Redis PING did not return success.")
    finally:
        await client.aclose()
