from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from rev_claude.configs import ROOT
from rev_claude.utils.poe_bots_utils import get_poe_bot_info


router = APIRouter()
templates = Jinja2Templates(directory=ROOT / "templates")

@router.get("/models")
async def show_models(request: Request):
    models = get_poe_bot_info()
    return templates.TemplateResponse(
        "models.html",
        {"request": request, "models": models}
    ) 