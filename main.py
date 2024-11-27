import argparse
import fire
import uvicorn
from fastapi import FastAPI
from loguru import logger
from rev_claude.client.client_manager import ClientManager
from rev_claude.configs import LOG_DIR
from rev_claude.lifespan import lifespan
from rev_claude.middlewares.register_middlewares import register_middleware
from rev_claude.router import router
from rev_claude.status.clients_status_manager import ClientsStatus
from utility import get_client_status

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="0.0.0.0", help="host")
parser.add_argument("--port", default=6238, help="port")
args = parser.parse_args()
logger.add(LOG_DIR / "log_file.log", rotation="1 week")  # 每周轮换一次文件
app = FastAPI(lifespan=lifespan)
app = register_middleware(app)


@app.get("/api/v1/clients_status")
async def _get_client_status():
    basic_clients, plus_clients = ClientManager().get_clients()
    all_status = await get_client_status(basic_clients, plus_clients)

    # Group by type and aggregate usage
    grouped_status = {}
    for status in all_status:
        client_type = status.type
        if client_type not in grouped_status:
            grouped_status[client_type] = status.model_dump()
            grouped_status[client_type]['usage'] = status.usage
        else:
            grouped_status[client_type]['usage'] += status.usage

    # Convert back to list format with one entry per type
    result = [ClientsStatus(**status) for status in grouped_status.values()]
    return result



def start_server(port=args.port, host=args.host):
    logger.info(f"Starting server at {host}:{port}")
    app.include_router(router)
    config = uvicorn.Config(app, host=host, port=port)
    server = uvicorn.Server(config=config)
    try:
        server.run()
    finally:
        logger.info("Server shutdown.")


if __name__ == "__main__":
    fire.Fire(start_server)
