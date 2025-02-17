# SPDX-License-Identifier: Apache-2.0

import asyncio
import functools

from fastapi import Request

from rev_claude.client.claude import save_base64_image
from rev_claude.openai_api.schemas import ChatMessage


async def extract_messages_and_images(messages: list[ChatMessage]):
    texts = []
    # base64_images = []
    image_paths = []
    roles = []
    for message in messages:
        role = message.role
        content = message.content
        roles.append(role)
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for item in content:
                message_type = item["type"]
                if message_type == "text":
                    texts.append(item["text"])
                elif message_type == "image_url":
                    base64_image = item["image_url"]["url"]
                    image_path = await save_base64_image(base64_image)
                    image_paths.append(image_path)
                else:
                    raise ValueError("Invalid message content type")
    messages = []
    for text, role in zip(texts, roles):
        messages.append(ChatMessage(role=role, content=text))
    return messages, image_paths


async def summarize_a_title(conversation_str: str, conversation_id, client_idx, api_key, client) -> str:
    prompt = f"""\
This a is a conversation:
{conversation_str}

Just give a short title(no more than 10 words) for it directly in language the conversation uses.
Title:"""
    response_text = ""
    model = "assistant"
    async for text in client.stream_message(
        prompt,
        conversation_id,
        model,
        client_type="plus",
        client_idx=client_idx,
        attachments=[],
        files=[],
        call_back=None,
        api_key=api_key,
        file_paths=[],
    ):
        response_text += text
    return response_text


async def listen_for_disconnect(request: Request) -> None:
    """Returns if a disconnect message is received"""
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            break


def with_cancellation(handler_func):
    """Decorator that allows a route handler to be cancelled by client
    disconnections.

    This does _not_ use request.is_disconnected, which does not work with
    middleware. Instead this follows the pattern from
    starlette.StreamingResponse, which simultaneously awaits on two tasks- one
    to wait for an http disconnect message, and the other to do the work that we
    want done. When the first task finishes, the other is cancelled.

    A core assumption of this method is that the body of the request has already
    been read. This is a safe assumption to make for fastapi handlers that have
    already parsed the body of the request into a pydantic model for us.
    This decorator is unsafe to use elsewhere, as it will consume and throw away
    all incoming messages for the request while it looks for a disconnect
    message.

    In the case where a `StreamingResponse` is returned by the handler, this
    wrapper will stop listening for disconnects and instead the response object
    will start listening for disconnects.
    """

    # Functools.wraps is required for this wrapper to appear to fastapi as a
    # normal route handler, with the correct request type hinting.
    @functools.wraps(handler_func)
    async def wrapper(*args, **kwargs):

        # The request is either the second positional arg or `raw_request`
        request = args[1] if len(args) > 1 else kwargs["raw_request"]

        handler_task = asyncio.create_task(handler_func(*args, **kwargs))
        cancellation_task = asyncio.create_task(listen_for_disconnect(request))

        done, pending = await asyncio.wait(
            [handler_task, cancellation_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        if handler_task in done:
            return handler_task.result()
        return None

    return wrapper
