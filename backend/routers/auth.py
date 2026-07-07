"""
backend/routers/auth.py
────────────────────────
Authentication router.

FIXES:
  - register() now auto-creates a Restaurant + 4 default Tables so that
    every AI endpoint finds a restaurant on first login. Without this,
    _get_restaurant() returned 404 and the frontend fell back to Lavy demo data.
  - Added /me endpoint returns restaurant_name so the frontend can
    personalise without an extra round-trip.
  - Added /restaurant PUT so the owner can update their name/address
    from the onboarding wizard.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models, auth
from pydantic import BaseModel
from routers.deps import get_restaurant_or_none

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ── Request / Response schemas ────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: str
    password: str
    tenant_name: str   # used as restaurant name on signup


class Token(BaseModel):
    access_token: str
    token_type: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RestaurantUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    currency: str | None = None
    timezone: str | None = None
    owner_phone: str | None = None   # E.164, e.g. +2547...; used for WhatsApp owner routing


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/register", response_model=Token)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    # Guard: duplicate email
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 1. Tenant
    tenant = models.Tenant(name=user_data.tenant_name)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    # 2. User
    hashed_password = auth.get_password_hash(user_data.password)
    new_user = models.User(
        email=user_data.email,
        hashed_password=hashed_password,
        role=models.Role.ADMIN,
        tenant_id=tenant.id,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Restaurant — THE MISSING PIECE.
    #    Without this every /ai/* endpoint returns 404 and the frontend
    #    falls back to the hardcoded "Lavy" demo data.
    restaurant = models.Restaurant(
        name=user_data.tenant_name,
        address="",
        tenant_id=tenant.id,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

    # 4. Seed 5 tables so the POS and reservations work immediately.
    for i in range(1, 6):
        db.add(models.Table(
            restaurant_id=restaurant.id,
            table_number=i,
            capacity=4,
            status=models.TableStatus.AVAILABLE,
        ))
    db.commit()

    access_token = auth.create_access_token(data={"sub": new_user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(login_data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == login_data.email).first()
    if not user or not auth.verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Returns user info + restaurant name for personalisation."""
    restaurant = get_restaurant_or_none(db, current_user)
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "restaurant_name": restaurant.name if restaurant else None,
        "restaurant_id": restaurant.id if restaurant else None,
    }


@router.put("/restaurant")
async def update_restaurant(
    data: RestaurantUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Onboarding wizard uses this to save restaurant profile."""
    restaurant = get_restaurant_or_none(db, current_user)
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if data.name is not None:
        restaurant.name = data.name
    if data.address is not None:
        restaurant.address = data.address
    if data.owner_phone is not None:
        restaurant.owner_phone = data.owner_phone
    db.commit()
    db.refresh(restaurant)
    return {
        "id": restaurant.id,
        "name": restaurant.name,
        "address": restaurant.address,
        "owner_phone": restaurant.owner_phone,
    }
