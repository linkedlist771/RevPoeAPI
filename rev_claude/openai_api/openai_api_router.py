from fastapi import APIRouter, Request, HTTPException, Header
from fastapi.responses import JSONResponse, StreamingResponse
import time
import json
import asyncio
import uuid
from rev_claude.openai_api.schemas import ChatCompletionRequest, ChatMessage
from rev_claude.client.claude_router import ClientManager
from uuid import uuid4

# Add this constant at the top of the file after the imports
VALID_API_KEY = "sk-test-123456789"

router = APIRouter()

def obtain_claude_client():
    basic_clients, plus_clients = ClientManager().get_clients()
    return {
        "basic_clients": basic_clients,
        "plus_clients": plus_clients,
    }

async def _async_resp_generator(original_generator, model: str):
    i = 0
    async for data in original_generator:
        chunk = {
                "id": i,
                "object": "chat.completion.chunk",
                "created": time.time(),
                "model": model,
                "choices": [{"delta": {"content": f"{data} "}}],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        i += 1

    yield "data: [DONE]\n\n"



async def streaming_message(request: ChatCompletionRequest, api_key: str = None):
    # Add API key validation
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
        
    clients = obtain_claude_client()
    model = request.model
    plus_clients = clients["plus_clients"]
    
    # Validate API key here if needed
    if not api_key:
        raise HTTPException(status_code=401, detail="API key is required")
    
    # done_data = build_sse_data(message="closed", id=conversation_id)
    client_idx = next(iter(plus_clients.keys()))
    claude_client = plus_clients[client_idx]
    client_type = "plus"

    conversation_id = str(uuid4())

    attachments = []
    files = []
    # This is a temporary solution to handle the case where the user uploads a file.
    file_paths = []
    messages = request.messages
    prompt = "\n".join([
        f"{message.role}: {message.content}" for message in messages
    ])


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
    request: ChatCompletionRequest,
    authorization: str = Header(None)
):
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided.")

    # Extract API key from Authorization header
    api_key = None
    if authorization:
        if authorization.startswith('Bearer'):
            api_key = authorization.replace('Bearer', '').strip()
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid Authorization header. Format should be 'Bearer YOUR_API_KEY'"
        )

    resp_content = await streaming_message(request, api_key=api_key)
    if request.stream:
        return StreamingResponse(
            _async_resp_generator(resp_content, request.model), media_type="text/event-stream"
        )

    return {
        "id": uuid.uuid4(),
        "object": "chat.completion",
        "created": time.time(),
        "model": request.model,
        "choices": [{"message": ChatMessage(role="assistant", content=resp_content)}],
    }