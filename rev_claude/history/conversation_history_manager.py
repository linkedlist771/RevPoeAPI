from datetime import datetime, timedelta
from redis.asyncio import Redis
from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, Field

from rev_claude.configs import REDIS_HOST, REDIS_PORT
from rev_claude.cookie.claude_cookie_manage import CookieKeyType
from rev_claude.models import ClaudeModels
from rev_claude.utils.time_zone_utils import get_shanghai_time


class RoleType(Enum):
    ASSISTANT = "assistant"
    USER = "user"


class Message(BaseModel):
    content: str
    role: RoleType
    timestamp: Optional[datetime] = Field(
        default_factory=lambda: datetime.utcnow() - timedelta(days=7)
    )
    message_attachment_file_paths: Optional[List[str]] = None


class ConversationHistory(BaseModel):
    conversation_id: str
    messages: List[Message]
    model: str


class ConversationHistoryRequestInput(BaseModel):
    client_idx: int
    conversation_type: CookieKeyType
    api_key: str
    conversation_id: Optional[str] = None
    page: int = Field(default=1, ge=1, description="Page number, starting from 1")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Number of items per page"
    )
    model: Any = None


class ConversationHistoryManager:

    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, db=0):
        """Initialize the connection to Redis."""
        # self.redis = redis.StrictRedis(host=host, port=port, db=db)
        self.host = host
        self.port = port
        self.db = db
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

    async def hgetall_async(self, key):
        return await (await self.get_aioredis()).hgetall(key)

    async def hget_async(self, key, field):
        return await (await self.get_aioredis()).hget(key, field)

    async def hset_async(self, key, field, value):
        await (await self.get_aioredis()).hset(key, field, value)

    def get_conversation_history_key(self, request: ConversationHistoryRequestInput):

        if request.conversation_type.value == "normal":
            return f"conversation_history-{request.api_key}-{request.client_idx}-basic"
        return f"conversation_history-{request.api_key}-{request.client_idx}-{request.conversation_type.value}"

    async def push_message(
        self, request: ConversationHistoryRequestInput, messages: list[Message]
    ):
        conversation_history_key = self.get_conversation_history_key(request)
        conversation_history_data = await self.hget_async(
            conversation_history_key, request.conversation_id
        )
        if conversation_history_data:
            conversation_history = ConversationHistory.model_validate_json(
                conversation_history_data
            )
            # 确保所有消息都有时间戳
            for message in messages:
                # if message.timestamp is None:
                message.timestamp = get_shanghai_time()
            conversation_history.messages.extend(messages)
        else:
            # 确保所有消息都有时间戳
            for message in messages:
                # if message.timestamp is None:
                message.timestamp = get_shanghai_time()
            conversation_history = ConversationHistory(
                conversation_id=request.conversation_id,
                messages=messages,
                model=request.model,
            )

        await self.hset_async(
            conversation_history_key,
            request.conversation_id,
            conversation_history.model_dump_json(),
        )

    async def get_conversation_histories(
        self, request: ConversationHistoryRequestInput
    ) -> List[ConversationHistory]:
        conversation_history_key = self.get_conversation_history_key(request)
        conversation_histories_data = await self.hgetall_async(conversation_history_key)
        histories = []

        for conversation_id, history_data in conversation_histories_data.items():
            history = ConversationHistory.model_validate_json(history_data)

            # 处理可能缺失的时间戳， 如果没有的话， 就返回初始时间戳, 就是刚开始的哪个1970年， 但是单位要和datetime.utcnow()一样

            default_time = datetime(1970, 1, 1)
            for message in history.messages:
                if message.timestamp is None:
                    message.timestamp = default_time
                    default_time = default_time.replace(
                        microsecond=default_time.microsecond + 1
                    )
            histories.append(history)
        histories.sort(
            key=lambda h: (
                h.messages[-1].timestamp.replace(tzinfo=None)
                if h.messages
                else datetime.min
            ),
            reverse=True,
        )

        return histories

    async def get_all_client_conversations(
        self, request: ConversationHistoryRequestInput
    ) -> List[ConversationHistory]:
        """Fetch and merge conversation histories from all clients for a given API key."""
        redis_client = await self.get_aioredis()

        # Get all keys matching the pattern conversation_history-{api_key}-*
        pattern = f"conversation_history-{request.api_key}-*"
        all_keys = await redis_client.keys(pattern)

        all_histories = []

        # Fetch histories from each matching key
        for key in all_keys:
            conversation_histories_data = await self.hgetall_async(key)

            for conversation_id, history_data in conversation_histories_data.items():
                history = ConversationHistory.model_validate_json(history_data)

                # Handle missing timestamps
                default_time = datetime(1970, 1, 1)
                for message in history.messages:
                    if message.timestamp is None:
                        message.timestamp = default_time
                        default_time = default_time.replace(
                            microsecond=default_time.microsecond + 1
                        )
                all_histories.append(history)

        # Sort all histories by the timestamp of their latest message
        all_histories.sort(
            key=lambda h: (
                h.messages[-1].timestamp.replace(tzinfo=None)
                if h.messages
                else datetime.min
            ),
            reverse=True,
        )

        return all_histories

    async def delete_all_conversations(self, request: ConversationHistoryRequestInput):
        conversation_history_key = self.get_conversation_history_key(request)
        # self.redis.delete(conversation_history_key)
        await (await self.get_aioredis()).delete(conversation_history_key)


def get_conversation_history_manager():
    return ConversationHistoryManager()


conversation_history_manager = ConversationHistoryManager()


# Example usage of the APIKeyManager
if __name__ == "__main__":
    manager = ConversationHistoryManager()
    request = ConversationHistoryRequestInput(
        client_idx=0,
        conversation_type=CookieKeyType.BASIC,
        api_key="sj-6d3f5d6",
        conversation_id="123",
        model=ClaudeModels.CLAUDE,
    )
