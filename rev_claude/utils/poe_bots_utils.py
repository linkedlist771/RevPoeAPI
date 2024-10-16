from functools import lru_cache
import json
from rev_claude.configs import POE_BOT_INFO


@lru_cache
def get_poe_bot_info():
    res =  json.loads(POE_BOT_INFO.read_text())
    # change each the key in the dict to lower case
    res = {k.lower(): v for k, v in res.items()}
    return res


if __name__ == "__main__":
    print(get_poe_bot_info())
