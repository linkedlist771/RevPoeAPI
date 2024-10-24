from functools import lru_cache
import json
from rev_claude.configs import POE_BOT_INFO, ALL_AVAILABLE_BOTS_INFORMATION_PATH


@lru_cache
def get_poe_bot_info():
    return json.loads(POE_BOT_INFO.read_text())


def get_all_available_poe_info():
    with ALL_AVAILABLE_BOTS_INFORMATION_PATH.open("r") as f:
        return json.load(f)


if __name__ == "__main__":
    print(get_poe_bot_info())
