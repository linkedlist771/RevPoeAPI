import asyncio
import traceback

from loguru import logger
from rev_claude.client.client_manager import ClientManager
from rev_claude.configs import DATA_DIR
from rev_claude.update_bots_infor.utils import get_available_bots, get_bot_information
from rev_claude.utils.json_utils import save_json, load_json
from tqdm import tqdm

BOTS_INFORMATION_DIR = DATA_DIR / "bots_information"  # this information
ALL_AVAILABLE_BOTS_FILE = BOTS_INFORMATION_DIR / "all_available_bots.json"
ALL_AVAILABLE_BOTS_INFORMATION_FILES = (
    BOTS_INFORMATION_DIR / "all_available_bots_information.json"
)


BOTS_INFORMATION_DIR.mkdir(exist_ok=True, parents=True)

# should be updated periodically


class PoeBotsUpdater:
    def __init__(self):
        # start to init the clients
        pass

    async def async_init(self):
        await ClientManager().load_clients(reload=False)

    async def save_updated_models(self, bots_count: int, get_all_bots: bool):
        all_bots_information = await get_available_bots(
            count=bots_count, get_all=get_all_bots
        )
        bots_size = len(all_bots_information)
        save_json(ALL_AVAILABLE_BOTS_FILE, all_bots_information)
        logger.debug(f"bots length:\n{bots_size}")

    async def save_models_information(self):
        # first load the model in to the json.
        bot_detailed_information = {}
        all_bots = load_json(ALL_AVAILABLE_BOTS_FILE)
        for bot_name, bot_info in tqdm(all_bots.items()):
            try:
                nickname = bot_info["bot"]["nickname"]
                handle = nickname
                bot_info = await get_bot_information(handle)
                bot_detailed_information[nickname] = bot_info
            except Exception as e:
                logger.error(f"error in {bot_name}")
                logger.error(e)
                logger.error(traceback.format_exc())
        save_json(ALL_AVAILABLE_BOTS_INFORMATION_FILES, bot_detailed_information)


async def amian():
    bots_count = 500
    get_all_bots = True
    poe_bots_updater = PoeBotsUpdater()
    await poe_bots_updater.async_init()
    await poe_bots_updater.save_models_information()


if __name__ == "__main__":
    asyncio.run(amian())
