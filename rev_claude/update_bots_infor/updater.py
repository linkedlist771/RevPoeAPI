import asyncio
from loguru import logger
from rev_claude.client.client_manager import ClientManager
from rev_claude.update_bots_infor.utils import get_available_bots


class PoeBotsUpdater:
    def __init__(self):
        # start to init the clients
        # ClientManager()
        pass

    async def async_init(self):
        await ClientManager().load_clients(reload=False)


async def amian():
    bots_count = 50
    get_all_bots = True
    poe_bots_updater = PoeBotsUpdater()
    await poe_bots_updater.async_init()
    all_bots_information = await get_available_bots(
        count=bots_count, get_all=get_all_bots
    )
    logger.debug(all_bots_information)


if __name__ == "__main__":
    asyncio.run(amian())
