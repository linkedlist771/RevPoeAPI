from functools import lru_cache
import json
from rev_claude.configs import POE_BOT_INFO


@lru_cache
def get_poe_bot_info():
    return json.loads(POE_BOT_INFO.read_text())

@lru_cache
def get_base_names():
    return [
        bot['baseModel'] for _, bot in get_poe_bot_info().items()
    ]

@lru_cache
def get_reverse_names_map():
    names = get_base_names()
    _names = list(get_poe_bot_info().keys())
    return {
        _name : name for name, _name in zip(names, _names)
    }


if __name__ == "__main__":
    print(get_poe_bot_info())
