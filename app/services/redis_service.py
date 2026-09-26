from redis.asyncio import Redis


class RedisService:
    """Technical Redis operations only: anti-spam, never business data."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def allow_request(self, key: str, limit: int, window_seconds: int) -> bool:
        """Atomically increment a fixed-window counter and check its limit."""
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.incr(key)
            pipeline.ttl(key)
            count, ttl = await pipeline.execute()
        if int(ttl) == -1:
            await self._redis.expire(key, window_seconds)
        return int(count) <= limit
