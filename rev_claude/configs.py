from httpx import Timeout
from pathlib import Path
import os

API_KEY_REFRESH_INTERVAL_HOURS = (
    99999999999  # 一天刷新一次, 用不刷新， 次数只能或者延期的时候获取。
)
ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
POE_BOT_INFO = DATA_DIR / "models.json"
API_KEY_REFRESH_INTERVAL = API_KEY_REFRESH_INTERVAL_HOURS * 60 * 60
# TODO: 这里增加使用次数次数改成对应增加对应的使用积分， 但是意思是一样的。
BASIC_KEY_MAX_USAGE = 30e4  # 普通用户一个月30万积分
PLUS_KEY_MAX_USAGE = 100e4  # plus 用户一个月。
ACCOUNT_DELETE_LIMIT = 1000000000


STREAM_CONNECTION_TIME_OUT = 60
STREAM_READ_TIME_OUT = 60
STREAM_POOL_TIME_OUT = 10 * 60
CLAUDE_CLIENT_LIMIT_CHECKS_INTERVAL_MINUTES = 10

NEW_CONVERSATION_RETRY = 5

# 设置连接超时为你的 STREAM_CONNECTION_TIME_OUT，其他超时设置为无限
STREAM_TIMEOUT = Timeout(
    connect=STREAM_CONNECTION_TIME_OUT,  # 例如设为 10 秒
    read=STREAM_READ_TIME_OUT,  # 例如设为 5 秒
    write=None,
    pool=STREAM_POOL_TIME_OUT,  # 例如设为 10 分钟
)

USE_PROXY = False
USE_MERMAID_AND_SVG = True

PROXIES = {"http://": "socks5://127.0.0.1:7891", "https://": "socks5://127.0.0.1:7891"}

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))


DOCS_USERNAME = "claude-backend"
DOCS_PASSWORD = "20Wd!!!!"


# Claude 官方镜像的链接w

CLAUDE_OFFICIAL_REVERSE_BASE_URL: str = "https://ai.liuli.arelay.com"

# 三小时
CLAUDE_OFFICIAL_EXPIRE_TIME = 3 * 60 * 60


# 每次使用都会增加20次次数
CLAUDE_OFFICIAL_USAGE_INCREASE = 15


"""
这里是对Poe后端的定义
"""
POE_BOT_BASE_URL = "https://api.poe.com/bot/"
POE_BOT_TEMPERATURE = 0.95


if __name__ == "__main__":
    from loguru import logger

    logger.info(ROOT)
