# from fastapi import APIRouter, Depends, HTTPException
#
#
# router = APIRouter()
#
#
# @router.get("/health")
# async def health():
#     return {"status": "ok"}
from fastapi import APIRouter, HTTPException
import time
import asyncio
from datetime import datetime

router = APIRouter()

# 记录启动时间
START_TIME = time.time()


@router.get("/health")
async def health():
    # 计算已运行时间（秒）
    running_time = time.time() - START_TIME

    # 如果运行时间超过60秒（1分钟），抛出异常
    if running_time > 60:
        raise HTTPException(status_code=500, detail="Service unhealthy")

    return {"status": "ok", "uptime": running_time}
