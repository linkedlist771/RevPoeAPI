import asyncio
import traceback
from typing import Dict, Any

import aiohttp
from blackd import handle
from loguru import logger
from rev_claude.configs import DATA_DIR
from rev_claude.update_bots_infor.utils import get_available_bots, get_bot_information
from rev_claude.utils.dict_utils import (
    remove_null_val_from_dict,
    make_dict_handle_lower,
)
from rev_claude.utils.json_utils import save_json, load_json
from tqdm import tqdm

# "photo_createe": {
#     "baseModel": "photocreatee",
#     "tokens": 2000,
#     "endpoints": [
#         "/v1/chat/completions"
#     ],
#     "premium_model": false,
#     "object": "model",
#     "owned_by": "poe",
#     "path": "assistant.svg",
#     "desc": "这个机器人可以生成逼真的图库照片、风格照片或动物照片。",
#     "text2image": true,
#     "points": 120
# },

from pydantic import BaseModel

from rev_claude.utils.poe_bots_utils import get_poe_bot_info, get_all_available_poe_info


class BotInformation(BaseModel):
    baseModel: str
    tokens: int
    endpoints: list[str]
    premium_model: bool
    object: str
    owned_by: str
    path: str
    desc: str
    text2image: bool
    points: int


BOTS_INFORMATION_DIR = DATA_DIR / "bots_information"  # this information
BOTS_AVATARS_DIR = DATA_DIR / "bots_avatars"  # this information
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
        from rev_claude.client.client_manager import ClientManager

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

    async def download_avatar(self, url: str, handle: str):
        """Download bot avatar from URL"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        avatar_path = BOTS_AVATARS_DIR / f"{handle}.png"
                        BOTS_AVATARS_DIR.mkdir(exist_ok=True, parents=True)
                        with open(avatar_path, 'wb') as f:
                            f.write(await response.read())
                        return True
        except Exception as e:
            logger.error(f"Error downloading avatar for {handle}: {e}")
            logger.error(traceback.format_exc())
        return False

    async def download_necessary_avatars(self):
        """Download avatars for filtered bots"""
        web_updated_bot_information = get_all_available_poe_info()
        web_updated_bot_information = remove_null_val_from_dict(web_updated_bot_information)
        web_updated_bot_information = {
            k: make_dict_handle_lower(v) for k, v in web_updated_bot_information.items()
        }

        for bot_name, bot_info in tqdm(web_updated_bot_information.items()):
            try:
                handle = bot_info["handle"]
                avatar_url = bot_info["picture"]["url"]

                # Check if avatar already exists
                avatar_path = BOTS_AVATARS_DIR / f"{handle}.png"
                if not avatar_path.exists():
                    success = await self.download_avatar(avatar_url, handle)
                    if success:
                        logger.info(f"Downloaded avatar for {handle}")
                    else:
                        logger.warning(f"Failed to download avatar for {handle}")
            except Exception as e:
                logger.error(f"Error processing avatar for {bot_name}: {e}")
                logger.error(traceback.format_exc())

    async def extract_filtered_bots(self) -> Dict[str, Any]:
        """Filter and process bots based on criteria"""
        filtered_bots = {}
        web_updated_bot_information = get_all_available_poe_info()
        web_updated_bot_information = remove_null_val_from_dict(web_updated_bot_information)
        web_updated_bot_information = {
            k: make_dict_handle_lower(v) for k, v in web_updated_bot_information.items()
        }

        for bot_name, bot_info in web_updated_bot_information.items():
            try:
                handle = bot_info["handle"]
                point = bot_info.get("messagePointLimit", {}).get("displayMessagePointPrice", 0)
                powered_by = bot_info.get("poweredBy", "")
                desc = bot_info.get("description", "")

                # Create bot information using pydantic model
                bot_data = BotInformation(
                    baseModel=handle,
                    tokens=2000,  # Default value, adjust as needed
                    endpoints=["/v1/chat/completions"],
                    premium_model=point > 0,
                    object="model",
                    owned_by=powered_by or "poe",
                    path=f"{handle}.png",
                    desc=desc,
                    text2image=False,  # Default value, adjust based on bot capabilities
                    points=point
                )

                filtered_bots[handle] = bot_data.dict()

            except Exception as e:
                logger.error(f"Error filtering bot {bot_name}: {e}")
                logger.error(traceback.format_exc())
        # use the local bots to update the information
        local_bots = get_poe_bot_info()
        filtered_bots.update(local_bots)
        # Save filtered bots information
        save_json(BOTS_INFORMATION_DIR / "filtered_bots.json", filtered_bots)
        return filtered_bots

# Update the main function
async def amain():
    bots_count = 500
    get_all_bots = True
    poe_bots_updater = PoeBotsUpdater()

    logger.info("Starting bot information update process")

    # Initialize and save basic model information
    await poe_bots_updater.async_init()
    await poe_bots_updater.save_updated_models(bots_count, get_all_bots)
    await poe_bots_updater.save_models_information()

    # Extract filtered bots and download avatars
    logger.info("Filtering bots and downloading avatars")
    filtered_bots = await poe_bots_updater.extract_filtered_bots()
    await poe_bots_updater.download_necessary_avatars()

    logger.info("Bot information update completed")
    return filtered_bots

if __name__ == "__main__":
    asyncio.run(amain())