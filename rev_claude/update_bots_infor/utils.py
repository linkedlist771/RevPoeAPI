from rev_claude.client.client_manager import ClientManager
from rev_claude.poe_api_wrapper import AsyncPoeApi
from loguru import logger
import asyncio
from tqdm.asyncio import tqdm
from typing import Dict, Any, Optional


async def get_first_plus_client(idx: int=0) -> AsyncPoeApi:
    basic_clients, plus_clients = ClientManager().get_clients()

    client = list(plus_clients.values())[idx]
    return await client.get_poe_bot_client()

async def get_available_bots(
    count: int = 25,
    get_all: bool = False,
) -> Dict[str, Any]:
    poe_client: AsyncPoeApi = await get_first_plus_client()
    all_bots = await poe_client.get_available_bots(count=count, get_all=get_all)

    return all_bots


async def get_all_explored_bots(
        count: int = 25,
        get_all: bool = False,) -> Dict[str, Any]:
    poe_client: AsyncPoeApi = await get_first_plus_client(idx=1)

    all_categories = await poe_client.get_available_categories()
    logger.debug(f"all_categories: \n{all_categories}")

    async def process_bot(bot: str) -> Optional[tuple[str, dict]]:
        try:
            bot_info = await poe_client.get_botInfo(handle=bot)
            nickname = bot_info['nickname']
            return nickname, bot_info
        except Exception as e:
            logger.error(f"Error processing bot {bot}: {str(e)}")
            return None
        finally:
            await asyncio.sleep(3)

    async def process_category(category: str) -> Optional[Dict[str, Any]]:
        try:
            bots = await poe_client.explore(categoryName=category, count=count, explore_all=get_all)
            # 处理每个category下的所有bot
            bot_results = await tqdm.gather(
                *[process_bot(bot) for bot in bots],
                desc=f"Processing bots in {category}"
            )
            # 过滤掉None结果
            return dict(result for result in bot_results if result is not None)
        except Exception as e:
            logger.error(f"Error processing category {category}: {str(e)}")
            return None
        finally:
            await asyncio.sleep(10)

    # 处理所有categories
    category_results = await tqdm.gather(
        *[process_category(category) for category in all_categories],
        desc="Processing categories"
    )

    # 合并所有结果,过滤掉None
    explored_bots = {}
    for category_result in category_results:
        if category_result is not None:
            explored_bots.update(category_result)

    return explored_bots
# handle 就是实际POE调用使用的模型的名字。


async def get_bot_information(handle: str):
    poe_client: AsyncPoeApi = await get_first_plus_client()
    bot_info = await poe_client.get_botInfo(handle=handle)
    return bot_info
