import json
import traceback
from os import write

from fastapi import APIRouter
from typing import List
from loguru import logger
from fastapi import Request
from fastapi.exceptions import RequestValidationError, HTTPException

from rev_claude.client.client_manager import ClientManager
from rev_claude.poe_api_wrapper import AsyncPoeApi

router = APIRouter()


@router.post("/get_available_bots")
async def get_available_bots(
    count: int = 25,
    get_all: bool = False,
):
    basic_clients, plus_clients = ClientManager().get_clients()
    client = next(iter(plus_clients.values()))
    poe_client: AsyncPoeApi = client.poe_bot_client
    all_bots = await poe_client.get_available_bots(count=count, get_all=get_all)
    return all_bots
    # basic_clients = [client.dict() for client in basic_clients.values()]

@router.post("/get_botInfo")
async def get_botInfo(
        handle: str
):
    basic_clients, plus_clients = ClientManager().get_clients()
    client = next(iter(plus_clients.values()))
    poe_client: AsyncPoeApi = client.poe_bot_client
    bot_infor = await poe_client.get_botInfo(handle=handle)
    return bot_infor
    # basic_clients = [client.dict() for client in basic_clients.values()]



