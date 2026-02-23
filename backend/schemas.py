from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from .models import QuoteStatus, MaterialType, ProcessType

class CustomerBase(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

class CustomerCreate(CustomerBase):
    pass

class Customer(CustomerBase):
    id: int
    created_at: datetime
    class Config:
        from_attributes = True

class QuoteLineItemBase(BaseModel):
    description: str
    material_type: Optional[MaterialType] = None
    process_type: Optional[ProcessType] = None
    quantity: float = 1.0
    unit: str = "ea"
    material_cost: float = 0.0
    labor_hours: float = 0.0
    notes: Optional[str] = None

class QuoteLineItemCreate(QuoteLineItemBase):
    pass

class QuoteLineItem(QuoteLineItemBase):
    id: int
    labor_cost: float
    line_total: float
    class Config:
        from_attributes = True

class QuoteBase(BaseModel):
    project_description: Optional[str] = None
    notes: Optional[str] = None
    labor_rate: float = 85.00
    markup: float = 1.35
    valid_days: int = 30

class QuoteCreate(QuoteBase):
    customer_id: int
    line_items: List[QuoteLineItemCreate] = []

class QuoteUpdate(BaseModel):
    status: Optional[QuoteStatus] = None
    project_description: Optional[str] = None
    notes: Optional[str] = None
    labor_rate: Optional[float] = None
    markup: Optional[float] = None

class Quote(QuoteBase):
    id: int
    quote_number: str
    customer_id: int
    status: QuoteStatus
    subtotal: float
    total: float
    created_at: datetime
    updated_at: datetime
    customer: Optional[Customer] = None
    line_items: List[QuoteLineItem] = []
    class Config:
        from_attributes = True

class MaterialPriceBase(BaseModel):
    material_type: MaterialType
    price_per_lb: Optional[float] = None
    price_per_sqft: Optional[float] = None
    price_per_foot: Optional[float] = None
    notes: Optional[str] = None

class MaterialPriceCreate(MaterialPriceBase):
    pass

class MaterialPrice(MaterialPriceBase):
    id: int
    updated_at: datetime
    class Config:
        from_attributes = True
