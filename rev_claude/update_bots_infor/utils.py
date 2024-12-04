from rev_claude.client.client_manager import ClientManager
from rev_claude.poe_api_wrapper import AsyncPoeApi
from loguru import logger
import asyncio
from tqdm.asyncio import tqdm
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asyncio
from typing import Dict, Any, Optional
from tqdm.asyncio import tqdm



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

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception)),
        reraise=True
    )
    async def process_bot(bot: str) -> Optional[tuple[str, dict]]:
        bot_info = await poe_client.get_botInfo(handle=bot)
        nickname = bot_info['nickname']
        return nickname, bot_info

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((Exception)),
        reraise=True
    )
    async def process_category(category: str) -> Optional[Dict[str, Any]]:
        results = {}

        try:
            bots = await poe_client.explore(categoryName=category, count=count, explore_all=get_all)

            for bot in tqdm(bots, desc=f"Processing bots in {category}"):
                try:
                    nickname, bot_info = await process_bot(bot)
                    if bot_info is not None:
                        results[bot] = bot_info  # 使用bot作为key
                except Exception as e:
                    logger.error(f"Error processing bot {bot}: {e}")
                    await asyncio.sleep(2)

            return results
        except Exception as e:
            logger.error(f"Error processing category {category}: {e}")
            return results

    # 使用asyncio.gather而不是tqdm.gather
    category_results = await asyncio.gather(
        *[process_category(category) for category in all_categories],
        return_exceptions=True
    )

    explored_bots = {}
    for category_result in category_results:
        if isinstance(category_result, dict):  # 确保结果是字典
            explored_bots.update(category_result)

    return explored_bots

# handle 就是实际POE调用使用的模型的名字。


async def get_bot_information(handle: str):
    poe_client: AsyncPoeApi = await get_first_plus_client()
    bot_info = await poe_client.get_botInfo(handle=handle)
    return bot_info
