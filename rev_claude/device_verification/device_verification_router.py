from loguru import logger
from rev_claude.api_key.api_key_manage import APIKeyManager, get_api_key_manager
from rev_claude.device_verification.device_verification_manager import (
    get_device_verification_manager,
    DeviceVerificationManager,
)
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import hashlib

router = APIRouter()

def get_request_device_id_hash(request: Request):
    """
    Generate a unique device ID hash for the user based on their User-Agent and IP address.
    """
    user_agent = request.headers.get("User-Agent", "")
    ip_address = request.client.host
    device_info = f"{user_agent}:{ip_address}".encode("utf-8")
    logger.debug(f"Device info: {device_info}")
    device_id = hashlib.sha256(device_info).hexdigest()
    return device_id

@router.get("/device/{api_key}/status")
async def get_device_status(
    api_key: str,
    request: Request,
    device_manager: DeviceVerificationManager = Depends(get_device_verification_manager),
    api_key_manager: APIKeyManager = Depends(get_api_key_manager),
):
    """
    Get the device verification status for a specific API key.
    """
    # Verify if the API key is valid
    is_valid = api_key_manager.is_api_key_valid(api_key)
    if not is_valid:
        return JSONResponse(
            content={
                "status": "invalid_api_key",
                "message": "Invalid API key. Please check the API key and try again.",
            },
            status_code=401,
        )

    device_id_from_redis = await device_manager.get_device_id(api_key)
    current_device_id = get_request_device_id_hash(request)

    logger.debug(f"Current device ID: {current_device_id}")
    logger.debug(f"Device ID from Redis: {device_id_from_redis}")

    if device_id_from_redis is None:
        # No device ID stored; user needs to update their device info
        return JSONResponse(
            content={
                "status": "no_device",
                "message": "No device registered for this API key.",
                "device_id": current_device_id,
            },
            status_code=200,
        )
    elif device_id_from_redis != current_device_id:
        # Device ID does not match; possible unauthorized access
        return JSONResponse(
            content={
                "status": "device_mismatch",
                "message": "Device mismatch. Please update your device info.",
                "device_id": current_device_id,
            },
            status_code=401,
        )

    # Device ID matches; verification successful
    return JSONResponse(
        content={
            "status": "verified",
            "message": "Device verified successfully.",
            "device_id": current_device_id,
        },
        status_code=200,
    )

@router.post("/device/{api_key}/update")
async def update_device_info(
    api_key: str,
    request: Request,
    device_manager: DeviceVerificationManager = Depends(get_device_verification_manager),
    api_key_manager: APIKeyManager = Depends(get_api_key_manager),
):
    """
    Update the stored device ID for a specific API key.
    """
    # Verify if the API key is valid
    is_valid = api_key_manager.is_api_key_valid(api_key)
    if not is_valid:
        return JSONResponse(
            content={
                "status": "invalid_api_key",
                "message": "Invalid API key. Please check the API key and try again.",
            },
            status_code=401,
        )
    current_device_id = get_request_device_id_hash(request)
    await device_manager.set_device_id(api_key, current_device_id)
    logger.debug(f"Updated device ID for API key {api_key}: {current_device_id}")

    return JSONResponse(
        content={
            "status": "updated",
            "message": "Device ID updated successfully.",
            "device_id": current_device_id,
        },
        status_code=200,
    )
