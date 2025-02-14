from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse, StreamingResponse
import time
import json
import asyncio
from loguru import logger
import uuid
from rev_claude.openai_api.schemas import ChatCompletionRequest, ChatMessage
from rev_claude.client.claude_router import ClientManager, select_client_by_usage
from uuid import uuid4
from rev_claude.configs import POE_OPENAI_LIKE_API_KEY
from rev_claude.openai_api.utils import extract_messages_and_images
from utility import get_client_status

# Add this constant at the top of the file after the imports
VALID_API_KEY = POE_OPENAI_LIKE_API_KEY

router = APIRouter()


def obtain_claude_client():
    basic_clients, plus_clients = ClientManager().get_clients()
    return {
        "basic_clients": basic_clients,
        "plus_clients": plus_clients,
    }


async def _async_resp_generator(original_generator, model: str):
    i = 0
    response_text = ""
    first_chunk = True
    async for data in original_generator:
        response_text += data
        if "</think>" in data:
            data_parts = data.split("</think>", 1)
            if len(data_parts) == 2:
                data_parts = [
                    data_parts[0],
                    "</think>\n",
                    data_parts[1],
                ]
            elif len(data_parts) == 1:
                data_parts = [
                    "</think>\n",
                ]
            for _data in data_parts:
                chunk = {
                    "id": i,
                    "object": "chat.completion.chunk",
                    "created": time.time(),
                    "model": model,
                    "choices": [
                        {
                            "delta": {
                                "content": f"{_data}",
                                **(
                                    {"role": "assistant"} if first_chunk else {}
                                ),  # 只在第一个chunk添加role
                            }
                        }
                    ],
                }
                first_chunk = False

                yield f"data: {json.dumps(chunk)}\n\n"
                i += 1

        else:

            chunk = {
                "id": i,
                "object": "chat.completion.chunk",
                "created": time.time(),
                "model": model,
                "choices": [
                    {
                        "delta": {
                            "content": f"{data}",
                            **(
                                {"role": "assistant"} if first_chunk else {}
                            ),  # 只在第一个chunk添加role
                        }
                    }
                ],
            }
            first_chunk = False

            yield f"data: {json.dumps(chunk)}\n\n"
            i += 1

    yield f"data: {json.dumps({'choices':[{"index": 0, "delta": {}, 
                                           "logprobs" : None, 
                                           "finish_reason" : 'stop'}]})}\n\n"
    yield "data: [DONE]\n\n"


async def streaming_message(request: ChatCompletionRequest, api_key: str = None):
    # Add API key validation
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    clients = obtain_claude_client()
    model = request.model
    # Validate API key here if needed
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")

    # done_data = build_sse_data(message="closed", id=conversation_id)
    basic_clients = clients["basic_clients"]
    plus_clients = clients["plus_clients"]
    client_type = "plus"
    client_idx = 0
    status_list = await get_client_status(basic_clients, plus_clients)
    claude_client = await select_client_by_usage(
        client_type, client_idx, basic_clients, plus_clients, status_list
    )

    # client_idx = next(iter(plus_clients.keys()))
    # claude_client = plus_clients[client_idx]

    conversation_id = str(uuid4())

    attachments = []
    files = []
    messages = request.messages
    messages, file_paths = await  extract_messages_and_images(messages)
    # logger.debug(f"Messages: {messages}")
    # logger.debug(f"File paths: {file_paths}")
    prompt = "\n".join(
        [f"{message.role}: {message.content}" for message in messages[:-1]]
    )
    last_message = messages[-1]
    request_model = request.model
    if "r1" in request_model.lower():
        force_think_template = """\
    上面是之前的历史记录,对于下面的问题，不管多简单，多复杂，都需要详细思考后给出答案。下面是你的回复格式:
    <think>
    # put your thinking here
    </think>"""
        prompt = prompt.replace(force_think_template, "")
        prompt += f"\n{force_think_template}\n"
    prompt += f"""{last_message.role}: {last_message.content}"""
    # logger.debug(f"Prompt: {prompt}")
    call_back = None
    if request.stream:
        streaming_res = claude_client.stream_message(
            prompt,
            conversation_id,
            model,
            client_type=client_type,
            client_idx=client_idx,
            attachments=attachments,
            files=files,
            call_back=call_back,
            api_key=api_key,
            file_paths=file_paths,
        )

        return streaming_res
    else:
        return "不支持非SSE"


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest, authorization: str = Header(None)
):
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    # Extract API key from Authorization header
    api_key = None
    if authorization:
        if authorization.startswith("Bearer"):
            api_key = authorization.replace("Bearer", "").strip()

    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Format should be 'Bearer YOUR_API_KEY'",
        )

    resp_content = await streaming_message(request, api_key=api_key)
    if request.stream:
        return StreamingResponse(
            _async_resp_generator(resp_content, request.model),
            media_type="text/event-stream",
        )

    return {
        "id": uuid.uuid4(),
        "object": "chat.completion",
        "created": time.time(),
        "model": request.model,
        "choices": [{"message": ChatMessage(role="assistant", content=resp_content)}],
    }
