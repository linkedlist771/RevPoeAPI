#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json, os, uuid
import re
import shutil
from datetime import datetime
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Union, List, Any
import numpy as np

# from curl_cffi import requests
import httpx
import asyncio

from httpx_sse._decoders import SSEDecoder
from loguru import logger
from fastapi import HTTPException

from rev_claude.REMINDING_MESSAGE import (
    NO_EMPTY_PROMPT_MESSAGE,
    PROMPT_TOO_LONG_MESSAGE,
    EXCEED_LIMIT_MESSAGE,
    PLUS_EXPIRE,
)
from rev_claude.configs import (
    STREAM_CONNECTION_TIME_OUT,
    # STREAM_TIMEOUT,
    PROXIES,
    USE_PROXY,
    CLAUDE_OFFICIAL_EXPIRE_TIME,
    CLAUDE_OFFICIAL_REVERSE_BASE_URL,
    USE_TOKEN_SHORTEN,
    ROOT,
    MAX_ATTACHMENTS,
    UPLOAD_DIR,
)

from rev_claude.models import ClaudeModels
from rev_claude.poe_api_wrapper import AsyncPoeApi
from rev_claude.status.clients_status_manager import ClientsStatusManager, ClientsStatus
from fastapi import UploadFile, status, HTTPException
from fastapi.responses import JSONResponse
import itertools
from rev_claude.status_code.status_code_enum import (
    HTTP_481_IMAGE_UPLOAD_FAILED,
    HTTP_482_DOCUMENT_UPLOAD_FAILED,
)
from rev_claude.utils.async_utils import remove_prefix, send_message_with_retry
from rev_claude.utils.cookie_utils import extract_cookie_value
from rev_claude.utils.file_utils import DocumentConverter
from rev_claude.utils.httpx_utils import async_stream
from rev_claude.utils.poe_bots_utils import get_poe_bot_info, get_base_names
from rev_claude.utils.sse_utils import build_sse_data


from fake_useragent import UserAgent

import uuid
import random
import os

from rev_claude.utils.token_utils import (
    get_token_length,
    shorten_message_given_prompt_length,
)


def generate_trace_id():
    # 生成一个随机的 UUID
    trace_id = uuid.uuid4().hex

    # 生成一个随机的 Span ID，长度为16的十六进制数
    span_id = os.urandom(8).hex()

    # 设定采样标识，这里假设采样率为1/10，即10%的数据发送
    sampled = random.choices([0, 1], weights=[9, 1])[0]

    # 将三个部分组合成完整的 Sentry-Trace
    sentry_trace = f"{trace_id}-{span_id}-{sampled}"
    return sentry_trace


async def save_file(file: UploadFile) -> str:
    upload_dir = UPLOAD_DIR
    # Create a directory to store uploaded files if it doesn't exist
    os.makedirs(upload_dir, exist_ok=True)

    # Generate a unique filename
    file_extension = Path(file.filename).suffix
    current_time = datetime.now().strftime("%Y_%m_%d_%H_%M_")
    unique_filename = f"{current_time}{uuid.uuid4()}{file_extension}"
    file_path = upload_dir / unique_filename

    try:
        # Save the file using shutil
        with file.file as source_file, open(file_path, "wb") as buffer:
            shutil.copyfileobj(source_file, buffer)
    except Exception as e:
        logger.error(f"Error saving file {file.filename}: {str(e)}")
        raise

    return str(file_path)  # Convert PosixPath to string


ua = UserAgent()
filtered_browsers = list(
    filter(
        lambda x: x["browser"] in ua.browsers
        and x["os"] in ua.os
        and x["percent"] >= ua.min_percentage,
        ua.data_browsers,
    )
)

# 使用itertools.cycle创建一个无限迭代器
infinite_iter = itertools.cycle(filtered_browsers)


def get_random_user_agent():
    return next(infinite_iter).get("useragent")


async def upload_attachment_for_fastapi(file: UploadFile):
    # 从 UploadFile 对象读取文件内容
    # 直接try to read
    try:
        document_converter = DocumentConverter(upload_file=file)
        result = await document_converter.convert()

        if result is None:
            logger.error(f"Unsupported file type: {file.filename}")
            # return JSONResponse(
            #     content={"message": "无法处理该文件类型"}, status_code=HTTP_482_DOCUMENT_UPLOAD_FAILED
            # )
            raise HTTPException(
                status_code=HTTP_482_DOCUMENT_UPLOAD_FAILED,
                detail="无法处理该文件类型",
            )

        return JSONResponse(content=result.model_dump())

    except Exception as e:
        logger.error(f"Meet Error when converting file to text: \n{e}")
        # return JSONResponse(content={"message": "处理上传文件报错"}, status_code=HTTP_482_DOCUMENT_UPLOAD_FAILED)
        raise HTTPException(
            status_code=HTTP_482_DOCUMENT_UPLOAD_FAILED,
            detail="处理上传文件报错",
        )


class Client:
    def format_cookie(self, cookie):
        # 去掉最后的; 用rstrip
        cookie = cookie.rstrip(";")
        return cookie

    def __init__(self, cookie, cookie_key=None):
        self.cookie = self.format_cookie(cookie)
        self.cookie_key = cookie_key
        self.poe_bot_client = None  # Add this line
        self.formkey = None
        # self.organization_id = self.get_organization_id()

    def __set_credentials__(self):
        p_b = extract_cookie_value(self.cookie, "p-b")
        p_lat = extract_cookie_value(self.cookie, "p-lat")
        # get the formkey

        self.p_b = p_b
        self.p_lat = p_lat
        if not self.p_b or not self.p_lat:
            raise ValueError("Invalid cookie")
        asyncio.create_task(self.update_poe_bot_client_tokens())  # Add

    def get_content_type(self, file_path):
        # Function to determine content type based on file extension
        extension = os.path.splitext(file_path)[-1].lower()
        if extension == ".pdf":
            return "application/pdf"
        elif extension == ".txt":
            return "text/plain"
        elif extension == ".csv":
            return "text/csv"
        # Add more content types as needed for other file types
        else:
            return "application/octet-stream"

    # Send and Response Stream Message to Claude
    @property
    def tokens(self):
        return {
            "p-b": self.p_b,
            "p-lat": self.p_lat,
        }

    async def get_remaining_credits(self) -> int:
        client = await self.get_poe_bot_client()
        settings = await client.get_settings()
        try:
            remaining_credits = settings["messagePointInfo"]["messagePointBalance"]
        except Exception:
            await asyncio.create_task(self.update_poe_bot_client_tokens())  # Add
            remaining_credits = 0
        return remaining_credits

    async def get_poe_bot_client(self):
        tokens = {
            "p-b": self.p_b,
            "p-lat": self.p_lat,
        }
        if not self.formkey:
            from rev_claude.cookie.claude_cookie_manage import get_cookie_manager

            cookie_manager = get_cookie_manager()

            formkey = await cookie_manager.get_cookie_formkey(self.cookie_key)
            logger.debug(f"formkey from redis:\n{formkey}")

            if formkey:
                tokens["formkey"] = formkey
                self.formkey = formkey
            else:
                self.poe_bot_client = await AsyncPoeApi(tokens=tokens).create()
                if (
                    self.poe_bot_client.formkey
                    and self.poe_bot_client.formkey != formkey
                ):
                    await cookie_manager.set_cookie_formkey(
                        self.cookie_key, self.poe_bot_client.formkey
                    )
        else:
            tokens["formkey"] = self.formkey
        if self.poe_bot_client is None:
            self.poe_bot_client = await AsyncPoeApi(tokens=tokens).create()

        return self.poe_bot_client

    async def renew_poe_bot_client(self):
        # Re-extract tokens from the cookie
        p_b = extract_cookie_value(self.cookie, "p-b")
        p_lat = extract_cookie_value(self.cookie, "p-lat")

        self.p_b = p_b
        self.p_lat = p_lat

        if not self.p_b or not self.p_lat:
            raise ValueError("Invalid cookie")

        # Re-fetch formkey from the cookie manager
        from rev_claude.cookie.claude_cookie_manage import get_cookie_manager

        cookie_manager = get_cookie_manager()
        formkey = await cookie_manager.get_cookie_formkey(self.cookie_key)
        logger.debug(f"formkey from redis in renew_poe_bot_client:\n{formkey}")

        tokens = {
            "p-b": self.p_b,
            "p-lat": self.p_lat,
        }

        if formkey:
            tokens["formkey"] = formkey
            self.formkey = formkey

        # Create a new poe_bot_client instance
        self.poe_bot_client = await AsyncPoeApi(tokens=tokens).create()

        # Update formkey in the cookie manager if it has changed
        if self.poe_bot_client.formkey and self.poe_bot_client.formkey != formkey:
            await cookie_manager.set_cookie_formkey(
                self.cookie_key, self.poe_bot_client.formkey
            )

    async def update_poe_bot_client_tokens(self):
        from rev_claude.cookie.claude_cookie_manage import get_cookie_manager

        if self.poe_bot_client:
            self.poe_bot_client.tokens = {
                "p-b": self.p_b,
                "p-lat": self.p_lat,
                "formkey": await get_cookie_manager().get_cookie_formkey(
                    self.cookie_key
                ),
            }

    async def stream_message(
        self,
        prompt,
        conversation_id,
        model,
        client_type,
        client_idx,
        attachments=None,
        files: Union[List[UploadFile], UploadFile, None] = None,
        call_back=None,
        api_key=None,
        timeout=120,
        file_paths=None,
    ):
        from rev_claude.history.conversation_history_manager import (
            ConversationHistoryRequestInput,
            conversation_history_manager,
        )

        conversation_history_request = ConversationHistoryRequestInput(
            client_idx=client_idx,
            conversation_type=client_type,
            api_key=api_key,
            conversation_id=conversation_id,
            model=model,
        )
        # TODO: temporary change it into all conversation histories
        all_histories = await conversation_history_manager.get_all_client_conversations(
            conversation_history_request
        )
        former_messages = []
        for history in all_histories:
            if history.conversation_id == conversation_id:
                former_messages = history.messages
                break
        #
        former_file_paths = []
        for message in former_messages:
            if message.message_attachment_file_paths:
                former_file_paths.extend(message.message_attachment_file_paths)
        if former_messages:
            former_messages = [
                {"role": message.role.value, "content": message.content}
                for message in former_messages
            ]
        if len(prompt) <= 0:
            yield NO_EMPTY_PROMPT_MESSAGE
            return
        if file_paths is None:
            file_paths = []
            # formatted_messages: list, bot_name: str
        former_file_paths.extend(file_paths)
        file_paths = former_file_paths[-MAX_ATTACHMENTS:]
        messages = [{"role": "user", "content": prompt}]
        former_messages.extend(messages)

        if USE_TOKEN_SHORTEN:
            tokens_limit = get_poe_bot_info()[model.lower()].get(
                "tokens", 4e3
            )  # default 4k tokens
            former_messages = shorten_message_given_prompt_length(
                former_messages, tokens_limit
            )

        messages = former_messages
        messages_str = "\n".join(
            [f"{message['role']}: {message['content']}" for message in messages]
        )

        response_text = ""
        if get_poe_bot_info()[model.lower()].get("text2image", None):
            messages_str = prompt
        logger.info(f"formatted_message: \n{messages_str}")
        poe_bot_client = await self.get_poe_bot_client()
        if model.lower() in get_base_names():
            model_name  = model.lower()
        else:
            model_name = get_poe_bot_info()[model.lower()]["baseModel"]
        logger.debug(f"actual model name: \n{model_name}")
        try:
            async for chunk in send_message_with_retry(
                poe_bot_client, model_name, messages_str, file_paths
            ):
                yield chunk
                response_text += chunk
        except RuntimeError as runtime_error:
            logger.error(f"RuntimeError: {runtime_error}")
            yield str(runtime_error)
        except Exception as e:
            from traceback import format_exc

            logger.error(f"Error: {format_exc()}")
            yield str(e)

        if call_back:
            if len(response_text) == 1:
                await call_back(response_text)
            else:
                await call_back[0](response_text)
                await call_back[1]()
            logger.info(f"Response text:\n {response_text}")
