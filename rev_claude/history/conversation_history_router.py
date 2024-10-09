from fastapi import APIRouter
from typing import List
from loguru import  logger
from scipy.stats import logistic_gen

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
    conversation_history_manager.push_message(request, messages)
    return {"message": "Message pushed successfully"}


@router.post("/get_conversation_histories")
async def get_conversation_histories(
    request: ConversationHistoryRequestInput,
) -> List[ConversationHistory]:
    """Get conversation histories."""
    try:
        histories = conversation_history_manager.get_conversation_histories(request)
        return histories

    except Exception as e:
        from traceback import format_exc
        logger.error(format_exc())


@router.post("/delete_all_conversations")
async def delete_all_conversations(
    request: ConversationHistoryRequestInput,
):
    """Delete all conversations for the current client."""
    conversation_history_manager.delete_all_conversations(request)
    return {"message": "All conversations deleted successfully"}
