import json
from uuid import uuid4
import redis
from enum import Enum
import time

from pydantic import BaseModel
from loguru import logger
from redis.asyncio import Redis
from rev_claude.configs import REDIS_HOST
from rev_claude.models import ClaudeModels


# from claude_cookie_manage import get_cookie_manager


class ClientStatus(Enum):
    ACTIVE = "active"
    ERROR = "error"
    BUSY = "busy"
    PART_CD = "part_cd"  # 部分账号cd
    CD = "cd"  # 等待刷新中。


class ClientsStatus(BaseModel):
    id: str
    status: str
    type: str
    idx: int
    message: str = ""
    is_session_login: bool = False
    usage: int = 0
    remaining: int = 0
    meta_data: dict = {}


class ClientsStatusManager:

    def __init__(self, host=REDIS_HOST, port=6379, db=2):
        """Initialize the connection to Redis."""
        self.host = host
        self.port = port
        self.db = db
        # self.redis = redis.StrictRedis(
        #     host=host, port=port, db=db, decode_responses=True
        # )

        self.aioredis = None

    async def get_aioredis(self):
        if self.aioredis is None:
            self.aioredis = await Redis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}", decode_responses=True
            )
        return self.aioredis

    async def decoded_get(self, key):
        res = await (await self.get_aioredis()).get(key)
        if isinstance(res, bytes):
            res = res.decode("utf-8")
        return res

    async def set_async(self, key, value):
        await (await self.get_aioredis()).set(key, value)

    async def exists_async(self, key):
        return await (await self.get_aioredis()).exists(key)

    def get_client_status_key(self, client_type, client_idx):
        return f"status-{client_type}-{client_idx}"

    def get_client_usage_key(self, client_type, client_idx):
        return f"usage-{client_type}-{client_idx}"

    # 先制作一个这个吧， 用于说明临近使用完了。
    def get_remaining_usage_key(self, client_type, client_idx):
        return f"remaining-{client_type}-{client_idx}"

    async def set_remaining_usage(self, client_type, client_idx, remaining):
        key = self.get_remaining_usage_key(client_type, client_idx)
        await self.set_async(key, remaining)

    async def get_remaining_usage(self, client_type, client_idx):
        key = self.get_remaining_usage_key(client_type, client_idx)
        return await self.decoded_get(key)

    def get_client_status_start_time_key(self, client_type, client_idx):
        return f"{self.get_client_status_key(client_type, client_idx)}:start_time"

    async def increment_usage(self, client_type, client_idx, increment=1):
        usage_key = self.get_client_usage_key(client_type, client_idx)
        return await (await self.get_aioredis()).incrby(usage_key, increment)

    async def set_usage(self, client_type, client_idx, usage):
        usage_key = self.get_client_usage_key(client_type, client_idx)
        await (await self.get_aioredis()).set(usage_key, usage)

    async def reset_usage(self, client_type, client_idx):
        usage_key = self.get_client_usage_key(client_type, client_idx)
        await (await self.get_aioredis()).set(usage_key, 0)

    async def get_usage(self, client_type, client_idx):
        usage_key = self.get_client_usage_key(client_type, client_idx)
        usage = await self.decoded_get(usage_key)
        #
        return int(usage) if usage is not None else 0

    async def get_limited_message(self, start_time_key, type, idx):
        # 获取账号状态
        client_status_key = self.get_client_status_key(type, idx)
        # status = self.redis.get(client_status_key)
        status = await self.decoded_get(client_status_key)
        if status == ClientStatus.ERROR.value:
            return "账号异常"
        # start_times = self.get_dict_value(start_time_key)
        start_times = await self.get_dict_value_async(start_time_key)

        message = ""
        current_time = time.time()

        for mode, start_time in start_times.items():

            # print(f"current_time: {current_time}, start_time: {start_time}")
            time_passed = current_time - float(start_time)
            remaining_time = 8 * 3600 - time_passed
            remaining_time = int(remaining_time)
            __mode = (
                mode.replace("claude-3-opus-20240229", "claude-3-opus")
                .replace("claude-3-5-sonnet-20240620", "claude-3.5-sonnet")
                .replace("claude-3-sonnet-20240229", "claude-3-sonnet")
            )
            if remaining_time > 0:
                message += f"{__mode}:需{remaining_time}秒。\n"
            else:
                message += f"{__mode}:可用。\n"
        return message

    async def get_dict_value_async(self, key):
        value = await self.decoded_get(key)
        if value is None:
            return {}
        try:
            res = json.loads(value)
            if not isinstance(res, dict):
                return {}
            else:
                return res
        except (json.JSONDecodeError, TypeError):
            return {}

    async def set_client_limited(self, client_type, client_idx, start_time, model):

        # 都得传入模型进行设置，我看这样设计就比较好了
        client_status_key = self.get_client_status_key(client_type, client_idx)
        # 设置键值对
        client_status_start_time_key = self.get_client_status_start_time_key(
            client_type, client_idx
        )
        # 首先判断这个是不是已经是cd状态了。
        # if self.redis.get(client_status_key) == ClientStatus.CD.value:
        #     return
        if await self.decoded_get(client_status_key) == ClientStatus.CD.value:
            return

        # self.redis.set(client_status_key, ClientStatus.CD.value)
        await self.set_async(client_status_key, ClientStatus.CD.value)
        # 这里就设计到另一个设计了，
        # 首先获取这个字典对应的值
        # start_time_dict = self.get_dict_value(client_status_start_time_key)
        start_time_dict = await self.get_dict_value_async(client_status_start_time_key)
        start_time_dict[model] = start_time
        # self.redis.set(client_status_start_time_key, json.dumps(start_time_dict))
        await self.set_async(client_status_start_time_key, json.dumps(start_time_dict))

    async def set_client_error(self, client_type, client_idx):
        client_status_key = self.get_client_status_key(client_type, client_idx)
        # self.redis.set(client_status_key, ClientStatus.ERROR.value)
        await self.set_async(client_status_key, ClientStatus.ERROR.value)

    async def set_client_active(self, client_type, client_idx):
        client_status_key = self.get_client_status_key(client_type, client_idx)
        # self.redis.set(client_status_key, ClientStatus.ACTIVE.value)
        await self.set_async(client_status_key, ClientStatus.ACTIVE.value)

    async def set_client_status(self, client_type, client_idx, status):
        client_status_key = self.get_client_status_key(client_type, client_idx)
        # self.redis.set(client_status_key, status)
        await self.set_async(client_status_key, status)

    async def set_client_active_when_cd(self, client_type, client_idx):
        client_status_key = self.get_client_status_key(client_type, client_idx)
        # status = self.redis.get(client_status_key)
        status = await self.decoded_get(client_status_key)
        if status == ClientStatus.CD.value:
            client_status_start_time_key = self.get_client_status_start_time_key(
                client_type, client_idx
            )
            current_time = time.time()
            # start_time_dict = self.get_dict_value(client_status_start_time_key)
            start_time_dict = await self.get_dict_value_async(
                client_status_start_time_key
            )
            for model, start_time in start_time_dict.items():
                time_elapsed = current_time - start_time
                if not (time_elapsed > 8 * 3600):
                    return False
            #
            # self.set_client_active(
            #     client_type, client_idx
            # )  # 有一个可用就是可用， 否则其他的都是CD
            await self.set_client_active(client_type, client_idx)
            # 然后重置使用次数
            await self.reset_usage(client_type, client_idx)
            # 这里把其设置为可用了
            return True
        elif status == ClientStatus.ACTIVE.value:
            return True
        else:
            return False

    async def create_if_not_exist(
        self, client_type: str, client_idx: int, models: list[str]
    ):
        client_status_key = self.get_client_status_key(client_type, client_idx)
        start_time_key = self.get_client_status_start_time_key(client_type, client_idx)
        # start_times = self.get_dict_value(start_time_key)
        start_times = await self.get_dict_value_async(start_time_key)
        # if (not self.redis.exists(client_status_key)) or (not start_times):
        #     self.redis.set(client_status_key, ClientStatus.ACTIVE.value)'
        usage_key = self.get_client_usage_key(client_type, client_idx)
        if (not await self.exists_async(client_status_key)) or (not start_times):
            await self.set_async(client_status_key, ClientStatus.ACTIVE.value)
            val = json.dumps({model: time.time() for model in models})
            # self.redis.set(
            #     self.get_client_status_start_time_key(client_type, client_idx), val
            # )
            await self.set_async(
                self.get_client_status_start_time_key(client_type, client_idx), val
            )
            await self.set_async(usage_key, 0)

    async def get_all_clients_status(self, basic_clients, plus_clients):
        from rev_claude.cookie.claude_cookie_manage import (
            get_cookie_manager,
        )

        async def retrieve_client_status(idx, client, client_type, models):
            await self.create_if_not_exist(client_type, idx, models)
            usage = await self.get_usage(client_type, idx)
            logger.debug(f"usage for redis: \n{usage}")
            if usage == 0:
                actual_usage = await client.get_remaining_credits()
                await self.set_usage(client_type, idx, actual_usage)
            account = await cookie_manager.get_account(client.cookie_key)
            _status = ClientStatus.ACTIVE.value
            client_type = "normal" if client_type == "basic" else client_type

            status = ClientsStatus(
                id=account,
                status=_status,
                type=client_type,
                idx=idx,
                message="",
                usage=usage,
                remaining=0,
            )
            return status

        async def process_clients(clients, client_type, models):
            """
            这个只处理是否为普通login的账号， 也就是说不为REVERSE_API_ONLY 就是OK的
            """

            status_list = []

            for idx, client in clients.items():
                status = await retrieve_client_status(idx, client, client_type, models)

                status_list.append(status)
            clients_status.extend(status_list)

        clients_status = []
        cookie_manager = get_cookie_manager()

        await process_clients(
            plus_clients,
            "plus",
            [ClaudeModels.OPUS.value, ClaudeModels.SONNET_3_5.value],
        )

        await process_clients(basic_clients, "basic", [ClaudeModels.SONNET_3_5.value])

        return clients_status
