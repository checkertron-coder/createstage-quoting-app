from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum


class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class JobType(str, enum.Enum):
    STRUCTURAL = "structural"
    ARCHITECTURAL = "architectural"
    SIGNAGE = "signage"
    LED_INTEGRATION = "led_integration"
    CUSTOM = "custom"


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
    CHANNEL = "channel"


class ProcessType(str, enum.Enum):
    LAYOUT = "layout"
    CUTTING = "cutting"
    CNC_PLASMA = "cnc_plasma"
    CNC_ROUTER = "cnc_router"
    WELDING = "welding"
    TIG_WELDING = "tig_welding"
    GRINDING = "grinding"
    DRILLING = "drilling"
    BENDING = "bending"
    ASSEMBLY = "assembly"
    DESIGN = "design"
    FIELD_INSTALL = "field_install"
    PROJECT_MANAGEMENT = "project_management"
    POWDER_COAT = "powder_coat"
    PAINT = "paint"


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


class ProcessRate(Base):
    """Per-process hourly rates — different processes charge differently."""
    __tablename__ = "process_rates"

    id = Column(Integer, primary_key=True, index=True)
    process_type = Column(Enum(ProcessType), unique=True, nullable=False)
    rate_per_hour = Column(Float, nullable=False)
    description = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    quote_number = Column(String, unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    status = Column(Enum(QuoteStatus), default=QuoteStatus.DRAFT)
    job_type = Column(Enum(JobType), default=JobType.CUSTOM)
    project_description = Column(Text)
    notes = Column(Text)
    # Rates
    labor_rate = Column(Float, default=125.00)          # Fallback if no process rate
    waste_factor = Column(Float, default=0.05)          # 5% material waste default
    contingency_pct = Column(Float, default=0.0)        # 0-25%
    profit_margin_pct = Column(Float, default=20.0)     # Internal margin (not shown on client quote)
    markup = Column(Float, default=1.0)                 # Legacy field — keep for compat
    # Totals
    subtotal = Column(Float, default=0.0)               # Before profit margin
    total = Column(Float, default=0.0)                  # After profit margin
    valid_days = Column(Integer, default=30)
    region = Column(String, default="chicago")
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

    # Quantity
    quantity = Column(Float, default=1.0)
    unit = Column(String, default="ea")

    # Dimensions (inches) — optional, for auto weight calc
    dim_length = Column(Float, nullable=True)
    dim_width = Column(Float, nullable=True)
    dim_thickness = Column(Float, nullable=True)
    weight_lbs = Column(Float, nullable=True)       # Can be auto-calc or manual
    waste_factor = Column(Float, nullable=True)     # Override quote-level waste factor

    # Material cost
    material_cost = Column(Float, default=0.0)      # Per unit, pre-waste

    # Labor
    labor_hours = Column(Float, default=0.0)
    process_rate_override = Column(Float, nullable=True)    # Override process rate table
    labor_cost = Column(Float, default=0.0)         # Calculated

    # Outsourced work (powder coat, laser cut, etc.)
    outsourced = Column(Boolean, default=False)
    outsource_service = Column(String, nullable=True)   # "powder_coat", "laser_cut", "sandblast"
    outsource_rate_per_sqft = Column(Float, nullable=True)
    sq_ft = Column(Float, nullable=True)            # For powder coat pricing

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
