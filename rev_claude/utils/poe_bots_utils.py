from functools import lru_cache
import json
from rev_claude.configs import POE_BOT_INFO



@lru_cache
def get_poe_bot_info():
    return json.loads(POE_BOT_INFO.read_text())




if __name__ == "__main__":
    print(get_poe_bot_info())