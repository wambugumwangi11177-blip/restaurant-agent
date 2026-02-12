from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# User Schemas
class UserBase(BaseModel):
    email: str

class UserCreate(UserBase):
    password: str
    tenant_name: str

class User(UserBase):
    id: int
    is_active: bool = True
    role: str

    class Config:
        from_attributes = True

# Token Schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None

# Menu Schemas
class MenuItemBase(BaseModel):
    name: str
    price: int # In cents
    category: str

class MenuItemCreate(MenuItemBase):
    pass

class MenuItemUpdate(MenuItemBase):
    name: Optional[str] = None
    price: Optional[int] = None
    category: Optional[str] = None

class MenuItem(MenuItemBase):
    id: int
    restaurant_id: int

    class Config:
        from_attributes = True
