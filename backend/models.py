from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum

class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"

class MaterialType(str, enum.Enum):
    MILD_STEEL = "mild_steel"
    STAINLESS_304 = "stainless_304"
    STAINLESS_316 = "stainless_316"
    ALUMINUM_6061 = "aluminum_6061"
    ALUMINUM_5052 = "aluminum_5052"
    DOM_TUBING = "dom_tubing"
    SQUARE_TUBING = "square_tubing"
    ANGLE_IRON = "angle_iron"
    FLAT_BAR = "flat_bar"
    PLATE = "plate"

class ProcessType(str, enum.Enum):
    CUTTING = "cutting"
    WELDING = "welding"
    BENDING = "bending"
    GRINDING = "grinding"
    DRILLING = "drilling"
    CNC_PLASMA = "cnc_plasma"
    CNC_ROUTER = "cnc_router"
    POWDER_COAT = "powder_coat"
    PAINT = "paint"
    ASSEMBLY = "assembly"
    DESIGN = "design"

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    company = Column(String)
    email = Column(String)
    phone = Column(String)
    address = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    quotes = relationship("Quote", back_populates="customer")

class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    status = Column(Enum(QuoteStatus), default=QuoteStatus.DRAFT)
    project_description = Column(Text)
    notes = Column(Text)
    labor_rate = Column(Float, default=85.00)
    markup = Column(Float, default=1.35)
    subtotal = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    valid_days = Column(Integer, default=30)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="quotes")
    line_items = relationship("QuoteLineItem", back_populates="quote", cascade="all, delete-orphan")

class QuoteLineItem(Base):
    __tablename__ = "quote_line_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"))
    description = Column(String, nullable=False)
    material_type = Column(Enum(MaterialType), nullable=True)
    process_type = Column(Enum(ProcessType), nullable=True)
    quantity = Column(Float, default=1.0)
    unit = Column(String, default="ea")
    material_cost = Column(Float, default=0.0)
    labor_hours = Column(Float, default=0.0)
    labor_cost = Column(Float, default=0.0)
    line_total = Column(Float, default=0.0)
    notes = Column(Text)

    quote = relationship("Quote", back_populates="line_items")

class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id = Column(Integer, primary_key=True, index=True)
    material_type = Column(Enum(MaterialType), unique=True, nullable=False)
    price_per_lb = Column(Float)
    price_per_sqft = Column(Float)
    price_per_foot = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(String)
