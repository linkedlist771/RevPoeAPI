from typing import List, Dict
from loguru import logger
import tiktoken
from functools import lru_cache
from rev_claude.configs import DEFAULT_TOKENIZER


@lru_cache
def get_tokenizer():
    return tiktoken.get_encoding(DEFAULT_TOKENIZER)




def get_token_length(prompt: str) -> int:
    return len(get_tokenizer().encode(prompt))


def shorten_message_given_prompt_length(messages: List[Dict], token_limits: int) -> List[Dict]:
    messages_str = "\n".join(
        [f"{message['role']}: {message['content']}" for message in messages]
    )
    token_length = get_token_length(messages_str)
    logger.debug(f"Token length: {token_length}")
    logger.debug(f"Token limits: {token_limits}")
    if token_length <= token_limits:
        return messages

    # too complicated , just keep the most recent messages,  remove the first two messages from the list if the role is not the system
    shortened_messages = messages.copy()
    removed_count = 0

    # Remove first 2 non-system messages
    i = 0
    while i < len(shortened_messages) and removed_count < 2:
        if shortened_messages[i]['role'] != 'system':
            shortened_messages.pop(i)
            removed_count += 1
        else:
            i += 1

    return shortened_messages
if __name__ == "__main__":
    print(get_token_length("hello world"))