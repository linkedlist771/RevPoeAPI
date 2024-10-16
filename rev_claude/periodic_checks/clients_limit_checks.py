import asyncio
import time
from tqdm.asyncio import tqdm
from rev_claude.configs import NEW_CONVERSATION_RETRY
from rev_claude.models import ClaudeModels
from loguru import logger

from rev_claude.status.clients_status_manager import ClientsStatusManager
from utility import get_client_status



async def __check_reverse_official_usage_limits():
    from rev_claude.client.client_manager import ClientManager

    start_time = time.perf_counter()
    basic_clients, plus_clients = ClientManager().get_clients()
    status_list = await get_client_status(basic_clients, plus_clients)
    clients = [
        {
            "client": (
                plus_clients[status.idx]
                if status.type == "plus"
                else basic_clients[status.idx]
            ),
            "type": status.type,
            "idx": status.idx,
        }
        for status in status_list
    ]
    logger.info(f"Found {len(clients)} active clients to check")
    async def check_client(client):
        try:
            logger.debug(f"Testing client {client['type']} {client['idx']}")
            usage = await client["client"].get_usage()
            clients_status_manager = ClientsStatusManager()
            await clients_status_manager.set_usage(client_type=client["type"], client_idx=client["idx"], usage=usage)

            return f"Client {client['type']} {client['idx']}: {usage}"
        except Exception as e:
            error_msg = f"Error testing client {client['type']} {client['idx']}: {e}"
            logger.error(error_msg)
            return error_msg

    async def process_batch(batch):
        return await asyncio.gather(*[check_client(client) for client in batch])

    results = []
    batch_size = 3  # 每批处理的客户端数量
    for i in range(0, len(clients), batch_size):
        batch = clients[i : i + batch_size]
        logger.info(
            f"Processing batch {i // batch_size + 1} of {len(clients) // batch_size + 1}"
        )
        batch_results = await process_batch(batch)
        results.extend(batch_results)
        if i + batch_size < len(clients):
            logger.info("Waiting between batches...")
            await asyncio.sleep(1)  # 批次之间的间隔

    logger.info("Completed check_reverse_official_usage_limits")

    # Print all results at the end
    logger.info("\nResults of client checks:")
    time_elapsed = time.perf_counter() - start_time
    logger.debug(f"Time elapsed: {time_elapsed:.2f} seconds")
    for result in results:
        logger.info(result)


async def check_reverse_official_usage_limits():
    # 使用 create_task，但不等待它完成
    task = asyncio.create_task(__check_reverse_official_usage_limits())
    return {"message": "Check started in background"}
