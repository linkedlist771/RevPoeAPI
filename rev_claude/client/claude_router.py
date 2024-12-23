import asyncio
from functools import partial
from pathlib import Path
from typing import Optional, List, Union, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import HTTPException, File, UploadFile, Form

from rev_claude.api_key.api_key_manage import APIKeyManager, get_api_key_manager

from rev_claude.client.claude import upload_attachment_for_fastapi, save_file
from rev_claude.client.client_manager import ClientManager
from rev_claude.configs import (
    NEW_CONVERSATION_RETRY,
    USE_MERMAID_AND_SVG,
    CLAUDE_OFFICIAL_USAGE_INCREASE,
)
from rev_claude.history.conversation_history_manager import (
    conversation_history_manager,
    ConversationHistoryRequestInput,
    Message,
    RoleType,
)
from rev_claude.prompts_builder.artifacts_render_prompt import ArtifactsRendererPrompt
from rev_claude.prompts_builder.svg_renderer_prompt import SvgRendererPrompt
from rev_claude.schemas import (
    ClaudeChatRequest,
    ObtainReverseOfficialLoginRouterRequest,
)
from loguru import logger

from rev_claude.models import ClaudeModels
from rev_claude.status.clients_status_manager import ClientsStatus
from rev_claude.status_code.status_code_enum import HTTP_480_API_KEY_INVALID
from rev_claude.utils.poe_bots_utils import get_poe_bot_info
from rev_claude.utils.sse_utils import build_sse_data
from utility import get_client_status
import numpy as np

# This in only for claude router, I do not use the


# async def validate_api_key(
#     api_key: str = Header(None), manager: APIKeyManager = Depends(get_api_key_manager)
# ):
async def validate_api_key(
    request: Request, manager: APIKeyManager = Depends(get_api_key_manager)
):

    api_key = request.headers.get("Authorization")
    # logger.info(f"checking api key: {api_key}")
    if api_key is None or not manager.is_api_key_valid(api_key):
        raise HTTPException(
            status_code=HTTP_480_API_KEY_INVALID,
            detail="APIKEY已经过期或者不存在，请检查您的APIKEY是否正确。",
        )
    # TODO: 这里增加使用次数次数改成对应增加对应的使用积分， 但是意思是一样的。
    # manager.increment_usage(api_key)
    logger.info(f"API key:\n{api_key}")
    logger.info(manager.get_apikey_information(api_key))
    # 尝试激活 API key
    active_message = manager.activate_api_key(api_key)
    logger.info(active_message)


async def increase_usage_callback(api_key, model):
    try:
        model_info = get_poe_bot_info()[model.lower()].get("points", 300)
        manager = get_api_key_manager()
        manager.increment_usage(api_key, model_info)
    except Exception as e:
        from traceback import format_exc

        logger.error(format_exc())


router = APIRouter(dependencies=[Depends(validate_api_key)])


def obtain_claude_client():

    basic_clients, plus_clients = ClientManager().get_clients()

    return {
        "basic_clients": basic_clients,
        "plus_clients": plus_clients,
    }


async def patched_generate_data(original_generator, conversation_id, hrefs=None):
    # 首先发送 conversation_id
    # 然后，对原始生成器进行迭代，产生剩余的数据
    async for data in original_generator:
        yield build_sse_data(message=data, id=conversation_id)
    if hrefs:
        for href in hrefs:
            yield build_sse_data(message=href, id=conversation_id)

    yield build_sse_data(message="closed", id=conversation_id)


@router.get("/list_models")
async def list_models():
    return [model.value for model in ClaudeModels]


@router.post("/convert_document")
async def convert_document(
    file: UploadFile = File(...),
):
    logger.info(f"Uploading file: {file.filename}")
    response = await upload_attachment_for_fastapi(file)
    return response


@router.post("/upload_image")
async def upload_image(
    file: UploadFile = File(...),
    client_idx: int = Form(...),
    client_type: str = Form(...),
    clients=Depends(obtain_claude_client),
):
    logger.info(f"Uploading file: {file.filename}")
    basic_clients = clients["basic_clients"]
    plus_clients = clients["plus_clients"]
    if client_type == "plus":
        claude_client = plus_clients[client_idx]
    else:
        claude_client = basic_clients[client_idx]
    response = await claude_client.upload_images(file)
    return response


async def push_assistant_message_callback(
    request: ConversationHistoryRequestInput,
    messages: list[Message],
    hrefs: list[str] = None,
    assistant_message: str = "",
):
    messages.append(
        Message(
            content=assistant_message,
            role=RoleType.ASSISTANT,
        )
    )
    if hrefs:
        hrefs_str = "".join(hrefs)
        messages[-1].content += hrefs_str

    await conversation_history_manager.push_message(request, messages)


async def select_client_by_usage(
    client_type: str,
    client_idx: int,
    basic_clients: dict,
    plus_clients: dict,
    status_list: List[ClientsStatus],
) -> Any:
    # 分别获取plus和basic的status
    plus_status = [s for s in status_list if s.type == "plus"]
    basic_status = [s for s in status_list if (s.type == "normal" or s.type == "basic")]
    # basic类型在status中标记为normal

    if client_type == "plus":
        if not plus_status:
            raise ValueError("No available plus clients")

        # 获取plus clients的usage值
        usages = [s.usage for s in plus_status]
        total_usage = sum(usages)

        # 如果总usage为0，使用均匀分布
        if total_usage == 0:
            probabilities = [1 / len(usages)] * len(usages)
        else:
            # 计算概率 - usage越大，概率越高
            probabilities = [usage / total_usage for usage in usages]

        # 对plus clients进行采样
        selected_idx = np.random.choice(len(plus_status), p=probabilities)
        selected_status = plus_status[selected_idx]
        return plus_clients[selected_status.idx]

    else:  # basic类型
        if not basic_status:
            raise ValueError("No available basic clients")

        # 获取basic clients的usage值
        usages = [s.usage for s in basic_status]
        total_usage = sum(usages)

        # 如果总usage为0，使用均匀分布
        if total_usage == 0:
            probabilities = [1 / len(usages)] * len(usages)
        else:
            # 计算概率 - usage越大，概率越高
            probabilities = [usage / total_usage for usage in usages]

        # 对basic clients进行采样
        selected_idx = np.random.choice(len(basic_status), p=probabilities)
        selected_status = basic_status[selected_idx]
        return basic_clients[selected_status.idx]


@router.post("/form_chat")
async def chat(
    request: Request,
    message: str = Form(...),
    conversation_id: Optional[str] = Form(None),
    model: str = Form(...),
    client_type: str = Form(...),
    client_idx: int = Form(...),
    stream: bool = Form(...),
    need_web_search: bool = Form(False),
    # attachments: Optional[List[str]] = Form(None),
    files: Union[List[UploadFile], UploadFile, None] = None,
    clients=Depends(obtain_claude_client),
    manager: APIKeyManager = Depends(get_api_key_manager),
):
    api_key = request.headers.get("Authorization")
    has_reached_limit = manager.has_exceeded_limit(api_key)
    if has_reached_limit:
        # is_deleted = not manager.is_api_key_valid(api_key)
        done_data = build_sse_data(message="closed", id=conversation_id)
        # TODO: fix this  message bug
        message = manager.generate_exceed_message(api_key)

        logger.info(f"API {api_key} has reached the limit.")
        return StreamingResponse(
            build_sse_data(message=message) + done_data, media_type="text/event-stream"
        )

    logger.info(
        f"Input chat request: message={message}, model={model}, client_type={client_type}, client_idx={client_idx}"
    )

    basic_clients = clients["basic_clients"]
    plus_clients = clients["plus_clients"]
    client_type = "plus" if client_type == "plus" else "basic"
    status_list = await get_client_status(basic_clients, plus_clients)
    claude_client = await select_client_by_usage(
        client_type, client_idx, basic_clients, plus_clients, status_list
    )

    raw_message = message
    if not conversation_id:
        conversation_id = str(uuid4())

    conversation_history_request = ConversationHistoryRequestInput(
        conversation_type=client_type,
        api_key=api_key,
        client_idx=client_idx,
        conversation_id=conversation_id,
        model=model,
    )
    messages: list[Message] = []


    attachments = []
    if not files:
        files = []
    # This is a temporary solution to handle the case where the user uploads a file.
    file_paths = []
    if files:
        if not isinstance(files, List):
            files = [files]
        for file in files:
            try:
                file_path = await save_file(file)
                file_paths.append(file_path)
            except Exception as e:
                logger.error(f"Error saving file {file.filename}: {str(e)}")
    messages.append(
        Message(
            content=raw_message,
            role=RoleType.USER,
            # attachments=[Path(path).name for path in file_paths]
            message_attachment_file_paths=file_paths,
        )
    )
    logger.debug(f"files: {files}")
    hrefs = []
    if need_web_search:
        from rev_claude.prompts_builder.duckduck_search_prompt import (
            DuckDuckSearchPrompt,
        )

        message, hrefs = await DuckDuckSearchPrompt(
            prompt=message,
        ).render_prompt()
        logger.info(f"Prompt After search: \n{message}")

    call_back = [
        partial(
            push_assistant_message_callback,
            conversation_history_request,
            messages,
            hrefs,
        ),
        partial(increase_usage_callback, api_key, model),
    ]

    if stream:
        streaming_res = claude_client.stream_message(
            message,
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
        streaming_res = patched_generate_data(streaming_res, conversation_id, hrefs)
        return StreamingResponse(
            streaming_res,
            media_type="text/event-stream",
        )
    else:
        return StreamingResponse(
            build_sse_data(message="不支持非SSE"),
            media_type="text/event-stream",
        )
