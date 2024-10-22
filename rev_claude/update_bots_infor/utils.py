from rev_claude.client.client_manager import ClientManager
from rev_claude.poe_api_wrapper import AsyncPoeApi
from loguru import logger

async def get_first_plus_client() -> AsyncPoeApi:
    basic_clients, plus_clients = ClientManager().get_clients()
    logger.debug(f"basic_clients: \n{basic_clients}")
    logger.debug(f"plus_clients: \n{plus_clients}")
    client = list(plus_clients.values())[0]
    return await client.get_poe_bot_client()


async def get_available_bots(
    count: int = 25,
    get_all: bool = False,
):
    poe_client: AsyncPoeApi = await get_first_plus_client()
    all_bots = await poe_client.get_available_bots(count=count, get_all=get_all)
    return all_bots


# handle 就是实际POE调用使用的模型的名字。


async def get_bot_information(handle: str):
    poe_client: AsyncPoeApi = await get_first_plus_client()
    bot_info = await poe_client.get_botInfo(handle=handle)
    return bot_info
