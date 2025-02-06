import asyncio
from tqdm.asyncio import tqdm
from loguru import logger
import traceback
from http.cookies import SimpleCookie
from functools import wraps


REGISTER_MAY_RETRY = 1
REGISTER_MAY_RETRY_RELOAD = 15  # in reload there are more retries

REGISTER_WAIT = 3


def remove_prefix(text, prefix):
    if text.startswith(prefix):
        return text[len(prefix) :].rstrip("\n")
    return text


def async_retry(retries=3, delay=1):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(retries):
                try:
                    async for chunk in func(*args, **kwargs):
                        yield chunk
                    return
                except (RuntimeError, Exception) as e:
                    if attempt == retries - 1:  # Last attempt
                        logger.error(f"Failed after {retries} attempts: {str(e)}")
                        error_prefix = "[ERROR] "  # 添加错误前缀
                        if isinstance(e, RuntimeError):
                            yield error_prefix + str(e)
                        else:
                            from traceback import format_exc
                            logger.error(f"Error: {format_exc()}")
                            yield error_prefix + str(e)
                    else:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                        await asyncio.sleep(delay)

        return wrapper

    return decorator


@async_retry(retries=3, delay=1)
async def send_message_with_retry(poe_bot_client, bot, message, file_path):
    prefixes = []

    try:
        async for chunk in poe_bot_client.send_message(
                bot=bot,
                message=message,
                file_path=file_path,
        ):
            text = chunk["response"]

            # 检查是否是错误消息
            if text.startswith("[ERROR] "):
                # yield text  # 将错误消息 yield 出去
                raise RuntimeError(text)  # 抛出 RuntimeError
                # return  # 终止生成器

            # 如果文本为空，跳过这个chunk
            if not text:
                continue

            # 如果文本不是只有换行符，将其添加到prefixes列表
            if text.rstrip("\n"):
                prefixes.append(text.rstrip("\n"))

            # 如果已经有至少两个前缀，移除当前文本中的上一个前缀
            if len(prefixes) >= 2:
                text = remove_prefix(text, prefixes[-2])

            # yield处理后的文本
            yield text

    except Exception as e:
        # 捕获任何异常，将其转换为错误消息并 yield 出去
        # error_message = f"<think> </think>[ERROR] An unexpected error occurred: {str(e)}"
        # yield error_message
        raise RuntimeError(f"An unexpected error occurred: {str(e)}")


async def _register_clients(
    cookie: str, cookie_key: str, cookie_type: str, reload: bool = False
):
    retry_count = REGISTER_MAY_RETRY if not reload else REGISTER_MAY_RETRY_RELOAD
    from rev_claude.cookie.claude_cookie_manage import get_cookie_manager
    from rev_claude.client.claude import Client

    cookie_manager = get_cookie_manager()
    while retry_count > 0:
        try:

            client = Client(cookie, cookie_key)
            client.__set_credentials__()

            return client
        except Exception as e:
            if "We are unable to serve your request" in str(e):
                retry_count -= 1
            else:
                retry_count = 0
            logger.error(f"error:" f"{str (e)}")
            logger.error(
                f"Failed to register the {cookie_type} client, retrying... {retry_count} retries left. \n Error: {traceback.format_exc()}"
            )
            if retry_count == 0:
                logger.error(
                    f"Failed to register the {cookie_type} client after several retries."
                )
                return None
            await asyncio.sleep(REGISTER_WAIT)  # 在重试前暂停1秒


async def register_clients(
    _basic_cookies,
    _basic_cookie_keys,
    _plus_cookies,
    _plus_cookie_keys,
    reload: bool = False,
):
    basic_tasks = []
    plus_tasks = []
    _basic_clients = []
    _plus_clients = []
    for plus_cookie, plus_cookie_key in zip(_plus_cookies, _plus_cookie_keys):
        task = asyncio.create_task(
            _register_clients(plus_cookie, plus_cookie_key, "plus", reload)
        )
        plus_tasks.append(task)

    for basic_cookie, basic_cookie_key in zip(_basic_cookies, _basic_cookie_keys):
        task = asyncio.create_task(
            _register_clients(basic_cookie, basic_cookie_key, "basic", reload)
        )
        basic_tasks.append(task)

    plus_clients = await asyncio.gather(*plus_tasks)
    basic_clients = await asyncio.gather(*basic_tasks)

    _basic_clients.extend(filter(None, basic_clients))
    _plus_clients.extend(filter(None, plus_clients))
    logger.debug(
        f"registered basic clients: {len(_basic_clients)} / {len(_basic_cookies)}"
    )
    logger.debug(
        f"registered plus clients: {len(_plus_clients)} / {len(_plus_cookies)}"
    )
    return _basic_clients, _plus_clients
