from typing import Union

from redis.asyncio import Redis

from rev_claude.configs import REDIS_HOST, REDIS_PORT


# 先用最简单的策略吧， 别想复杂了。

# 每个apikey对应一个设备的device_id


class DeviceVerificationManager:

    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, db=1):
        """Initialize the connection to Redis."""
        self.host = host
        self.port = port
        self.db = db
        self.aioredis = None

    async def get_aioredis(self):
        if self.aioredis is None:
            self.aioredis = await Redis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}"
            )
        return self.aioredis

    async def decoded_get(self, key):
        res = await (await self.get_aioredis()).get(key)
        if isinstance(res, bytes):
            res = res.decode("utf-8")
        return res

    async def async_set(self, key, value):
        await (await self.get_aioredis()).set(key, value)

    def get_device_verification_key(self, api_key: str):
        return f"{api_key}:device_id"

    async def get_device_id(self, api_key: str) -> Union[str, None]:
        device_id_key = self.get_device_verification_key(api_key)
        device_id = await self.decoded_get(device_id_key)
        return device_id

    async def set_device_id(self, api_key: str, device_id: str):
        device_id_key = self.get_device_verification_key(api_key)
        await self.async_set(device_id_key, device_id)
        return True


def get_device_verification_manager():
    return DeviceVerificationManager()
