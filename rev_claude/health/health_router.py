


from fastapi import APIRouter, Depends, HTTPException



router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}