#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json, os, uuid
import re
import shutil
from http.cookies import SimpleCookie
from typing import Union, List

from poe_api_wrapper import AsyncPoeApi

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
    STREAM_TIMEOUT,
    PROXIES,
    USE_PROXY,
    CLAUDE_OFFICIAL_EXPIRE_TIME,
    CLAUDE_OFFICIAL_REVERSE_BASE_URL,
)

from rev_claude.models import ClaudeModels
from rev_claude.status.clients_status_manager import ClientsStatusManager
from fastapi import UploadFile, status, HTTPException
from fastapi.responses import JSONResponse
import itertools
from rev_claude.status_code.status_code_enum import (
    HTTP_481_IMAGE_UPLOAD_FAILED,
    HTTP_482_DOCUMENT_UPLOAD_FAILED,
)
from rev_claude.utils.cookie_utils import extract_cookie_value
from rev_claude.utils.file_utils import DocumentConverter
from rev_claude.utils.httpx_utils import async_stream
from rev_claude.utils.poe_bots_utils import get_poe_bot_info
from rev_claude.utils.sse_utils import build_sse_data


from fake_useragent import UserAgent

import uuid
import random
import os


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


def remove_prefix(text, prefix):
    # logger.debug(f"text: \n{text}")
    # logger.debug(f"prefix: \n{prefix}")
    # logger.debug(text.startswith(prefix))
    if text.startswith(prefix):
        return text[len(prefix) :].rstrip("\n")
    return text


async def save_file(file: UploadFile) -> str:
    # Create a directory to store uploaded files if it doesn't exist
    upload_dir = "uploaded_files"
    os.makedirs(upload_dir, exist_ok=True)

    # Generate a unique filename
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(upload_dir, unique_filename)

    try:
        # Save the file using shutil
        with file.file as source_file, open(file_path, "wb") as buffer:
            shutil.copyfileobj(source_file, buffer)
    except Exception as e:
        logger.error(f"Error saving file {file.filename}: {str(e)}")
        raise

    return file_path


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

    async def __set_organization_id__(self):
        self.organization_id = await self.__async_get_organization_id()
        return self.organization_id

    def retrieve_session_key(self):
        cookie_list = self.cookie.split(";")
        for cookie_key_pair in cookie_list:
            if "sk-ant-si" in cookie_key_pair:
                return cookie_key_pair.strip().replace("sessionKey=", "")
        return

    def build_organization_headers(self):
        return {
            "User-Agent": get_random_user_agent(),
            # "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/124.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://claude.ai/chats",
            "Content-Type": "application/json",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
        }

    async def __async_get_organization_id(self):
        url = "https://claude.ai/api/organizations"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url, headers=self.build_organization_headers()
                )
                res_str = response.text
                logger.debug(f"res_str : {res_str}")
                res = response.json()
                if "We are unable to serve your request" in res_str:
                    raise Exception("We are unable to serve your request")
                logger.debug(f"res : {res}")
                uuid = res[0]["uuid"]
                return uuid

            except Exception as e:
                import traceback

                logger.error(traceback.format_exc())

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

    # Lists all the conversations you had with Claud

    # Send Message to Claude

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
        from rev_claude.cookie.claude_cookie_manage import get_cookie_manager
        cookie_manager = get_cookie_manager()
        formkey = await cookie_manager.get_cookie_formkey(self.cookie_key)
        tokens = {
            "p-b": self.p_b,
            "p-lat": self.p_lat,
        }
        if formkey:
            tokens["formkey"] = formkey

        if self.poe_bot_client is None:
            self.poe_bot_client = await AsyncPoeApi(tokens=tokens).create()

        if self.poe_bot_client.formkey and self.poe_bot_client.formkey != formkey:
            await cookie_manager.set_cookie_formkey(self.cookie_key, self.poe_bot_client.formkey)

        return self.poe_bot_client

    async def update_poe_bot_client_tokens(self):
        from rev_claude.cookie.claude_cookie_manage import get_cookie_manager

        if self.poe_bot_client:
            self.poe_bot_client.tokens = {
                "p-b": self.p_b,
                "p-lat": self.p_lat,
                "formkey": await get_cookie_manager().get_cookie_formkey(self.cookie_key)
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
        all_histories = await conversation_history_manager.get_conversation_histories(
            conversation_history_request
        )
        former_messages = []
        for history in all_histories:
            if history.conversation_id == conversation_id:
                former_messages = history.messages
                break
        #
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
        messages = [{"role": "user", "content": prompt}]
        former_messages.extend(messages)
        messages = former_messages
        messages_str = "\n".join(
            [f"{message['role']}: {message['content']}" for message in messages]
        )
        response_text = ""
        if get_poe_bot_info()[model.lower()].get("text2image", None):
            messages_str = prompt
        logger.info(f"formatted_messages: {messages_str}")
        prefixes = []

        poe_bot_client = await self.get_poe_bot_client()

        try:
            async for chunk in poe_bot_client.send_message(
                bot=get_poe_bot_info()[model.lower()]["baseModel"],
                message=messages_str,
                file_path=file_paths,
            ):
                text = chunk["response"]
                # prefixes = text
                if not text:
                    continue
                if text.rstrip("\n"):
                    prefixes.append(text.rstrip("\n"))
                if len(prefixes) >= 2:
                    # logger.debug(f"prefixes: \n{prefixes}")
                    # logger.debug(f"text before remove prefix: \n{text}")
                    text = remove_prefix(text, prefixes[-2])
                    # logger.debug(f"text after remove prefix: \n{text}")
                yield text
                response_text += text
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

    # Deletes the conversation
    def delete_conversation(self, conversation_id):
        url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"
        payload = json.dumps(f"{conversation_id}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/124.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Content-Length": "38",
            "Referer": "https://claude.ai/chats",
            "Origin": "https://claude.ai",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
            "TE": "trailers",
        }

        response = requests.delete(
            url, headers=headers, data=payload, impersonate="chrome110"
        )

        # Returns True if deleted or False if any error in deleting
        if response.status_code == 204:
            return True
        else:
            return False

    # Returns all the messages in conversation
    def chat_conversation_history(self, conversation_id):
        url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/124.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://claude.ai/chats",
            "Content-Type": "application/json",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
        }

        response = requests.get(url, headers=headers, impersonate="chrome110")

        # List all the conversations in JSON
        return response.json()

    def generate_uuid(self):
        random_uuid = uuid.uuid4()
        random_uuid_str = str(random_uuid)
        formatted_uuid = f"{random_uuid_str[0:8]}-{random_uuid_str[9:13]}-{random_uuid_str[14:18]}-{random_uuid_str[19:23]}-{random_uuid_str[24:]}"
        return formatted_uuid

    def build_new_chat_headers(self, uuid):
        return {
            # "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "User-Agent": get_random_user_agent(),
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": f"https://claude.ai/chat/{uuid}",
            "Content-Type": "application/json",
            "Origin": "https://claude.ai",
            "DNT": "1",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "TE": "trailers",
        }

    def build_get_conversation_histories_headers(self, url_path):
        return {
            "Alt-Svc": "h3=':443'; ma=86400",
            "Cf-Cache-Status": "DYNAMIC",
            # "Cf-Ray": "89a7300dae7c827c-TPE",
            "Content-Encoding": "br",
            # "Content-Security-Policy": "script-src 'strict-dynamic' 'wasm-unsafe-eval' https: 'nonce-17ba8129-a77d-4672-b23d-4662a4cbb39d'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'; block-all-mixed-content; upgrade-insecure-requests",
            "Content-Type": "application/json",
            # "Date": "Thu, 27 Jun 2024 17:34:25 GMT",
            "Server": "cloudflare",
            "Set-Cookie": self.cookie,
            # f"activitySessionId=ad8f37d8-d54a-4730-be0a-c86e39b90f30; Path=/; Expires=Fri, 28 Jun 2024 05:34:25 GMT; Secure; HttpOnly; SameSite=lax",
            "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
            "Vary": "RSC, Next-Router-State-Tree, Next-Router-Prefetch, Next-Url",
            "Via": "1.1 google",
            "X-Activity-Session-Id": "ad8f37d8-d54a-4730-be0a-c86e39b90f30",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "SAMEORIGIN",
            "X-Request-Pathname": url_path,
            # "/api/organizations/dc00b293-7c1c-43f9-ac4a-d14d501e73ca/chat_conversations/0796759-9efe-4875-9984-8dc2021640bc",
            "X-Xss-Protection": "1; mode=block",
        }

    async def get_conversation_histories(self, conversation_id):
        # Q:与prefix相对的是什么
        # A: 与prefix相对的是suffix
        path = f"/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"
        # url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations/{conversation_id}"
        url = f"https://claude.ai{path}"
        headers = self.build_get_conversation_histories_headers(path)
        async with httpx.AsyncClient(
            # proxies=PROXIES if USE_PROXY else None,
            timeout=STREAM_CONNECTION_TIME_OUT,
        ) as client:
            response = await client.get(url, headers=headers)
        return response.json()

    async def create_new_chat(self, model):
        url = f"https://claude.ai/api/organizations/{self.organization_id}/chat_conversations"
        uuid = self.generate_uuid()
        # payload = json.dumps({"uuid": uuid, "name": "", "model": model})
        payload = {"uuid": uuid, "name": ""}

        headers = self.build_new_chat_headers(uuid)
        # logger.debug(f"headers: \n{headers}")
        # logger.debug(f"payload: \n{payload}")
        async with httpx.AsyncClient(
            # proxies=PROXIES if USE_PROXY else None,
            timeout=STREAM_CONNECTION_TIME_OUT,
        ) as client:
            response = await client.post(url, headers=headers, json=payload)
        return response.json()

    # Resets all the conversations
    def reset_all(self):
        conversations = self.list_all_conversations()

        for conversation in conversations:
            conversation_id = conversation["uuid"]
            delete_id = self.delete_conversation(conversation_id)

        return True

    def upload_attachment(self, file_path):
        if file_path.endswith(".txt"):
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_type = "text/plain"
            with open(file_path, "r", encoding="utf-8") as file:
                file_content = file.read()

            return {
                "file_name": file_name,
                "file_type": file_type,
                "file_size": file_size,
                "extracted_content": file_content,
            }
        url = "https://claude.ai/api/convert_document"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/124.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://claude.ai/chats",
            "Origin": "https://claude.ai",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
            "TE": "trailers",
        }

        file_name = os.path.basename(file_path)
        content_type = self.get_content_type(file_path)

        files = {
            "file": (file_name, open(file_path, "rb"), content_type),
            "orgUuid": (None, self.organization_id),
        }

        response = requests.post(url, headers=headers, files=files)
        if response.status_code == 200:
            return response.json()
        else:
            return False

    async def upload_images(self, image_file: UploadFile):

        url = f"https://claude.ai/api/{self.organization_id}/upload"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/124.0",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://claude.ai/chats",
            "Origin": "https://claude.ai",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Connection": "keep-alive",
            "Cookie": self.cookie,
            "TE": "trailers",
        }
        time_out = 10
        try:
            async with httpx.AsyncClient(timeout=time_out) as client:
                response = await client.post(
                    url,
                    headers=headers,
                    files={
                        "file": (
                            image_file.filename,
                            image_file.file,
                            image_file.content_type,
                        )
                    },
                )
                logger.info(f"response: \n{response.json()} ")
                if response.status_code == 200:
                    res_json = response.json()
                    return JSONResponse(content=res_json)

                else:
                    # return JSONResponse(
                    #     content={"message": "Failed to upload image"},
                    #     status_code=HTTP_481_IMAGE_UPLOAD_FAILED,
                    # )
                    raise HTTPException(
                        status_code=HTTP_481_IMAGE_UPLOAD_FAILED,
                        detail="Failed to upload image",
                    )

        except Exception as e:
            logger.error(f"Failed to upload image: {e}")
            raise HTTPException(
                status_code=HTTP_481_IMAGE_UPLOAD_FAILED,
                detail="Failed to upload image",
            )
