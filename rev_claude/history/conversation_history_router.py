import json
import traceback

from fastapi import APIRouter
from typing import List
from loguru import logger
from fastapi import Request
from fastapi.exceptions import RequestValidationError, HTTPException
from pydantic import ValidationError

from rev_claude.history.conversation_history_manager import (
    ConversationHistoryManager,
    ConversationHistoryRequestInput,
    ConversationHistory,
    Message,
    conversation_history_manager,
)

router = APIRouter()


def get_conversation_history_manager():
    return ConversationHistoryManager()


@router.post("/push_message")
async def push_message(
    request: ConversationHistoryRequestInput,
    messages: List[Message],
):
    """Push a message to conversation history."""
    await conversation_history_manager.push_message(request, messages)
    return {"message": "Message pushed successfully"}


# @router.post("/get_conversation_histories")
# async def get_conversation_histories(
#     request: ConversationHistoryRequestInput,
# ) -> List[ConversationHistory]:
#     """Get conversation histories."""
#     try:
#         histories = await conversation_history_manager.get_conversation_histories(request)
#         return histories
#
#     except Exception as e:
#         from traceback import format_exc
#         logger.error(format_exc())


@router.post("/get_conversation_histories")
async def get_conversation_histories(request: Request) -> List[ConversationHistory]:
    """Get conversation histories."""
    try:
        # 手动解析请求数据
        raw_data = await request.json()
        # 尝试创建 ConversationHistoryRequestInput 实例
        input_data = ConversationHistoryRequestInput(**raw_data)
        page = input_data.page
        page_size = input_data.page_size
        histories = await conversation_history_manager.get_all_client_conversations(
            input_data
        )
        # 计算总记录数和总页数
        total_records = len(histories)
        total_pages = (total_records + page_size - 1) // page_size

        # 计算当前页的起始和结束索引
        start_index = (page - 1) * page_size
        end_index = min(start_index + page_size, total_records)

        # 获取当前页的对话历史
        paginated_histories = histories[start_index:end_index]
        return paginated_histories
        # return histories

    except ValidationError as ve:
        # 捕获 Pydantic 验证错误
        logger.error(f"Validation error: {ve}")
        error_messages = [f"{error['loc'][0]}: {error['msg']}" for error in ve.errors()]
        raise HTTPException(status_code=422, detail={"errors": error_messages})

    except RequestValidationError as rve:
        # 捕获 FastAPI 请求验证错误
        logger.error(f"Request validation error: {rve}")
        error_messages = [
            f"{error['loc'][-1]}: {error['msg']}" for error in rve.errors()
        ]
        raise HTTPException(status_code=422, detail={"errors": error_messages})

    except json.JSONDecodeError as jde:
        # 捕获 JSON 解析错误
        logger.error(f"JSON decode error: {jde}")
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")

    except Exception as e:
        # 捕获其他所有异常
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/delete_all_conversations")
async def delete_all_conversations(
    request: ConversationHistoryRequestInput,
):
    """Delete all conversations for the current client."""
    conversation_history_manager.delete_all_conversations(request)
    return {"message": "All conversations deleted successfully"}
