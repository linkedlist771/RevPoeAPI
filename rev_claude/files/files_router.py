from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import FileResponse
from pathlib import Path

from rev_claude.configs import UPLOAD_DIR
from rev_claude.files.utils import get_file_name

router = APIRouter()


@router.get("/uploaded_files/{file_path:path}")
async def get_file(file_path: str):
    file_path = get_file_name(file_path)
    # 构建完整的文件路径
    full_path = UPLOAD_DIR / file_path

    try:
        # 确保文件路径在BASE_DIR内，防止目录遍历攻击
        full_path = full_path.resolve()
        if not str(full_path).startswith(str(UPLOAD_DIR.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        # 检查文件是否存在
        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        # 返回文件
        return FileResponse(path=full_path)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/uploaded_files")
async def list_files():
    # 禁止直接访问文件夹
    raise HTTPException(status_code=403, detail="Directory listing not allowed")
