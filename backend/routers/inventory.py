from fastapi import APIRouter, Depends

router = APIRouter(prefix="/inventory", tags=["inventory"])

@router.get("/")
async def get_inventory():
    return []

@router.post("/deduct")
async def deduct_inventory(item_id: int, quantity: int):
    return {"status": "deducted"}
