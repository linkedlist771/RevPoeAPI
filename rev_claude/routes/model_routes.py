from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from rev_claude.configs import ROOT
from rev_claude.utils.poe_bots_utils import get_poe_bot_info
from typing import Optional


router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "templates")

@router.get("/models")
async def show_models(request: Request, page: int = 1, per_page: int = 9):
    models = get_poe_bot_info()
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    paginated_models = dict(list(models.items())[start_idx:end_idx])
    total_pages = (len(models) + per_page - 1) // per_page
    
    return templates.TemplateResponse(
        "models.html",
        {
            "request": request, 
            "models": paginated_models,
            "current_page": page,
            "total_pages": total_pages,
            "total_models": len(models)
        }
    )

@router.get("/api/search-models")
async def search_models(query: str):
    models = get_poe_bot_info()
    query = query.lower()
    
    filtered_models = {
        model_id: model_info 
        for model_id, model_info in models.items()
        if query in model_info.get("baseModel", "").lower() or 
           query in model_info.get("desc", "").lower()
    }
    
    return JSONResponse(content=filtered_models) 