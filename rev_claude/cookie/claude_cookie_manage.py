import asyncio

import redis
import uuid
from enum import Enum
from typing import Tuple, List
from loguru import logger
from rev_claude.client.claude import Client
from rev_claude.configs import REDIS_HOST, REDIS_PORT
from rev_claude.utils.async_utils import register_clients


class CookieKeyType(Enum):
    PLUS = "plus"
    BASIC = "basic"
    TEST = "test"
    NORMAL = "normal"


class CookieManager:

    def __init__(self, host=REDIS_HOST, port=REDIS_PORT, db=1):
        """Initialize the connection to Redis."""
        self.redis = redis.StrictRedis(host=host, port=port, db=db)

    def get_cookie_type_key(self, cookie_key):
        return f"{cookie_key}:type"

    def get_cookie_account_key(self, cookie_key):
        return f"{cookie_key}:account"

    def get_cookie_organization_key(self, cookie_key):
        return f"{cookie_key}:organization"

    def update_organization_id(self, cookie_key, organization_id):
        organization_key = self.get_cookie_organization_key(cookie_key)
        self.redis.set(organization_key, organization_id)
        return f"Organization ID for {cookie_key} has been updated."

    def delete_organization_id(self, cookie_key):
        organization_key = self.get_cookie_organization_key(cookie_key)
        if self.redis.exists(organization_key):
            self.redis.delete(organization_key)
            return f"Organization ID for {cookie_key} has been deleted."
        else:
            return f"No organization found for {cookie_key}. Nothing to delete."

    def get_organization_id(self, cookie_key):
        organization_key = self.get_cookie_organization_key(cookie_key)
        organization_id = self.redis.get(organization_key)
        return organization_id.decode("utf-8") if organization_id else None

    # 这里设置一下账号和cookie的type方便后面检索。

    # 暂时不设置过期时间，因为我也不知道过期时间是啥时候
    def upload_cookie(
        self, cookie: str, cookie_type=CookieKeyType.BASIC.value, account=""
    ):
        """Upload a new cookie with a specific expiration time."""
        cookie_key = f"cookie-{str(uuid.uuid4()).replace('-', '')}"
        self.redis.set(cookie_key, cookie)
        type_key = self.get_cookie_type_key(cookie_key)
        self.redis.set(type_key, cookie_type)
        account_key = self.get_cookie_account_key(cookie_key)
        self.redis.set(account_key, account)
        return cookie_key

    def update_cookie(self, cookie_key: str, cookie: str, account: str = ""):
        self.redis.set(cookie_key, cookie)
        account_key = self.get_cookie_account_key(cookie_key)
        self.redis.set(account_key, account)
        return f"Cookie {cookie_key} has been updated."

    def delete_cookie(self, cookie_key: str):
        """Delete a cookie."""
        self.redis.delete(cookie_key)
        type_key = self.get_cookie_type_key(cookie_key)
        self.redis.delete(type_key)
        account_key = self.get_cookie_account_key(cookie_key)
        self.redis.delete(account_key)
        return f"Cookie {cookie_key} has been deleted."

    def get_cookie_status(self, cookie_key: str):
        type_key = self.get_cookie_type_key(cookie_key)
        account_key = self.get_cookie_account_key(cookie_key)
        _type = self.redis.get(type_key)
        account = self.redis.get(account_key)
        return f"{cookie_key}: \n type: {_type} \n account: {account}"

    def get_account(self, cookie_key: str):
        account_key = self.get_cookie_account_key(cookie_key)
        return self.redis.get(account_key)

    def get_all_cookies(self, cookie_type: str):
        """Retrieve all cookies of a specified type."""
        pattern = f"*:type"
        cursor = 0
        cookies = []
        cookies_keys = []

        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=1000)
            for key in keys:
                actual_type = self.redis.get(key).decode("utf-8")
                if actual_type == cookie_type:
                    base_key = key.decode("utf-8").split(":type")[0]
                    cookie_value = self.redis.get(base_key)
                    if cookie_value:
                        cookies.append(cookie_value.decode("utf-8"))
                        cookies_keys.append(base_key)

            if cursor == 0:
                break

        return cookies, cookies_keys

    def get_all_cookie_status(self):
        pattern = f"*:type"
        cursor = 0
        cookies = []
        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=1000)
            for key in keys:
                actual_type = self.redis.get(key).decode("utf-8")
                base_key = key.decode("utf-8").split(":type")[0]
                cookie_value = self.redis.get(base_key)
                account_key = self.get_cookie_account_key(base_key)
                account = self.redis.get(account_key).decode("utf-8")
                if cookie_value:
                    cookies.append(
                        {
                            "cookie": cookie_value,
                            "type": actual_type,
                            "account": account,
                        }
                    )

            if cursor == 0:
                break

        return cookies

    # 还是重启一下比较好哎。
    async def get_all_basic_and_plus_client(
        self, reload: bool = False
    ) -> Tuple[List[Client], List[Client]]:
        _basic_cookies, _basic_cookie_keys = self.get_all_cookies(
            CookieKeyType.BASIC.value
        )
        _plus_cookies, _plus_cookie_keys = self.get_all_cookies(
            CookieKeyType.PLUS.value
        )
        _basic_clients, _plus_clients = await register_clients(
            _basic_cookies, _basic_cookie_keys, _plus_cookies, _plus_cookie_keys, reload
        )
        return _basic_clients, _plus_clients

    def get_all_cookie_status(self):
        pattern = f"*:type"
        cursor = 0
        cookies = []

        while True:
            cursor, keys = self.redis.scan(cursor, match=pattern, count=1000)
            for key in keys:
                actual_type = self.redis.get(key).decode("utf-8")
                base_key = key.decode("utf-8").split(":type")[0]
                cookie_value = self.redis.get(base_key)
                account_key = self.get_cookie_account_key(base_key)
                account = self.redis.get(account_key)
                if cookie_value:
                    cookies.append(
                        f"{base_key}: \n type: {actual_type} \n account: {account}"
                    )

            if cursor == 0:
                break

        return cookies


def get_cookie_manager():
    return CookieManager()


# Example usage of the APIKeyManager
if __name__ == "__main__":
    manager = CookieManager()
    print(manager.upload_cookie("test_cookie", CookieKeyType.TEST.value))
