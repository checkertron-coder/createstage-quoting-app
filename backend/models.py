from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey, Enum, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
import enum


# --- Enums (kept for existing tables that use them) ---

class QuoteStatus(str, enum.Enum):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"


# DECISION: JobType enum removed in v2 — job_type is now a VARCHAR field so adding
# new types doesn't require a migration. See V2_JOB_TYPES below for valid values.


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


# --- v2 Job Types — authoritative list (Sessions 1-8) ---
# Use as validation reference. Stored as VARCHAR, not enum.

V2_JOB_TYPES = [
    # Priority A — gates & railings
    "cantilever_gate",
    "swing_gate",
    "straight_railing",
    "stair_railing",
    "repair_decorative",
    # Priority B — structural & architectural
    "ornamental_fence",
    "complete_stair",
    "spiral_stair",
    "window_security_grate",
    "balcony_railing",
    # Priority C — specialty
    "furniture_table",
    "utility_enclosure",
    "bollard",
    "repair_structural",
    "custom_fab",
    # Priority D — automotive
    "offroad_bumper",
    "rock_slider",
    "roll_cage",
    "exhaust_custom",
    # Priority E — industrial & signage
    "trailer_fab",
    "structural_frame",
    "furniture_other",
    "sign_frame",
    "led_sign_custom",
    # Priority F — products
    "product_firetable",
]


# --- v2 New Tables ---

class User(Base):
    """Multi-tenant shop accounts."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)  # Nullable for provisional accounts
    is_verified = Column(Boolean, default=False)
    is_provisional = Column(Boolean, default=True)
    shop_name = Column(String, nullable=True)
    shop_address = Column(Text, nullable=True)
    shop_phone = Column(String, nullable=True)
    shop_email = Column(String, nullable=True)
    logo_url = Column(String, nullable=True)
    rate_inshop = Column(Float, default=125.00)
    rate_onsite = Column(Float, default=145.00)
    markup_default = Column(Integer, default=15)
    tier = Column(String, default="free")  # 'free' | 'starter' | 'professional' | 'shop'
    subscription_status = Column(String, default="free")  # 'free' | 'active' | 'past_due' | 'cancelled'
    trial_ends_at = Column(DateTime, nullable=True)
    invite_code_used = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    terms_accepted_at = Column(DateTime, nullable=True)
    quotes_this_month = Column(Integer, default=0)
    billing_cycle_start = Column(DateTime, nullable=True)
    deposit_labor_pct = Column(Integer, default=50)
    deposit_materials_pct = Column(Integer, default=100)
    email_verified = Column(Boolean, default=False)
    onboarding_complete = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    auth_tokens = relationship("AuthToken", back_populates="user", cascade="all, delete-orphan")
    quote_sessions = relationship("QuoteSession", back_populates="user", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="user", foreign_keys="Quote.user_id")
    shop_equipment = relationship("ShopEquipment", back_populates="user", uselist=False, cascade="all, delete-orphan")


class AuthToken(Base):
    """JWT refresh token storage — access tokens are stateless."""
    __tablename__ = "auth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String, nullable=False)
    token_type = Column(String, default="refresh")  # 'access' | 'refresh'
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="auth_tokens")


class QuoteSession(Base):
    """Conversation state across the 6-stage pipeline."""
    __tablename__ = "quote_sessions"

    id = Column(String, primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    job_type = Column(String, nullable=True)
    stage = Column(String, default="intake")  # Current pipeline stage
    params_json = Column(JSON, default=dict)  # Accumulated QuoteParams
    messages_json = Column(JSON, default=list)  # Conversation history
    photo_urls = Column(JSON, default=list)  # Cloudflare R2 URLs
    status = Column(String, default="active")  # 'active' | 'complete' | 'abandoned'
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="quote_sessions")


class HardwareItem(Base):
    """Parts pricing with 3-option sourcing (McMaster, Amazon, other)."""
    __tablename__ = "hardware_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)  # 'hinge' | 'latch' | 'operator' | etc.
    mcmaster_part = Column(String, nullable=True)
    mcmaster_price = Column(Float, nullable=True)
    mcmaster_url = Column(String, nullable=True)
    alt1_supplier = Column(String, nullable=True)
    alt1_price = Column(Float, nullable=True)
    alt1_url = Column(String, nullable=True)
    alt2_supplier = Column(String, nullable=True)
    alt2_price = Column(Float, nullable=True)
    alt2_url = Column(String, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow)


class HistoricalActual(Base):
    """Labor accuracy tracking — compare estimates vs. actual hours."""
    __tablename__ = "historical_actuals"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True)
    actual_hours_by_process = Column(JSON, nullable=True)  # {process: actual_hours}
    actual_material_cost = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    variance_pct = Column(Float, nullable=True)  # vs. estimated
    recorded_at = Column(DateTime, default=datetime.utcnow)

    quote = relationship("Quote", back_populates="historical_actuals")


# --- Existing Tables (preserved, extended where needed) ---

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
    quotes = relationship("Quote", back_populates="customer", foreign_keys="Quote.customer_id")


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
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    # DECISION: job_type changed from Enum(JobType) to String — no migration needed for new types
    job_type = Column(String, default="custom_fab")
    status = Column(Enum(QuoteStatus), default=QuoteStatus.DRAFT)
    project_description = Column(Text)
    notes = Column(Text)
    # Rates
    labor_rate = Column(Float, default=125.00)
    waste_factor = Column(Float, default=0.05)
    material_markup_pct = Column(Float, default=15.0)
    stainless_multiplier = Column(Float, default=1.0)
    contingency_pct = Column(Float, default=0.0)
    profit_margin_pct = Column(Float, default=20.0)
    markup = Column(Float, default=1.0)  # Legacy field — keep for compat
    # Totals
    subtotal = Column(Float, default=0.0)
    total = Column(Float, default=0.0)
    valid_days = Column(Integer, default=30)
    region = Column(String, default="chicago")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # --- v2 columns ---
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    session_id = Column(String, nullable=True)
    inputs_json = Column(JSON, nullable=True)  # QuoteParams snapshot
    outputs_json = Column(JSON, nullable=True)  # PricedQuote snapshot
    selected_markup_pct = Column(Integer, default=15)
    pdf_url = Column(String, nullable=True)  # Cloudflare R2 URL

    # Relationships
    customer = relationship("Customer", back_populates="quotes", foreign_keys=[customer_id])
    user = relationship("User", back_populates="quotes", foreign_keys=[user_id])
    line_items = relationship("QuoteLineItem", back_populates="quote", cascade="all, delete-orphan")
    historical_actuals = relationship("HistoricalActual", back_populates="quote")


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
    weight_lbs = Column(Float, nullable=True)
    waste_factor = Column(Float, nullable=True)

    # Material cost
    material_cost = Column(Float, default=0.0)

    # Labor
    labor_hours = Column(Float, default=0.0)
    process_rate_override = Column(Float, nullable=True)
    labor_cost = Column(Float, default=0.0)

    # Outsourced work (powder coat, laser cut, etc.)
    outsourced = Column(Boolean, default=False)
    outsource_service = Column(String, nullable=True)
    outsource_rate_per_sqft = Column(Float, nullable=True)
    sq_ft = Column(Float, nullable=True)

    line_total = Column(Float, default=0.0)
    notes = Column(Text)

    quote = relationship("Quote", back_populates="line_items")


class BidAnalysis(Base):
    """Stored bid document analysis — users may revisit extractions."""
    __tablename__ = "bid_analyses"

    id = Column(String, primary_key=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=True)
    page_count = Column(Integer, nullable=True)
    extraction_confidence = Column(Float, nullable=True)
    items_json = Column(JSON, nullable=True)     # List of ExtractedItem
    warnings_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class InviteCode(Base):
    """Beta invite codes for free tier access."""
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False, index=True)
    tier = Column(String, default="professional")  # tier granted to user
    max_uses = Column(Integer, nullable=True)  # null = unlimited
    uses = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class DemoLink(Base):
    """48-hour magic links for frictionless demos."""
    __tablename__ = "demo_links"

    id = Column(Integer, primary_key=True, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    label = Column(String, nullable=True)  # "For Jim Lai", "Investor demo"
    tier = Column(String, default="professional")
    max_quotes = Column(Integer, default=3)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    used_at = Column(DateTime, nullable=True)
    demo_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailToken(Base):
    """Single-use tokens for password reset and email verification."""
    __tablename__ = "email_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    token_type = Column(String, nullable=False)  # 'password_reset' | 'email_verification'
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class ShopEquipment(Base):
    """Shop equipment profile — stores capabilities parsed from onboarding."""
    __tablename__ = "shop_equipment"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    # Structured capabilities (JSON)
    welding_processes = Column(JSON, default=list)      # [{"process": "MIG", "primary": true, "wire_type": "flux core", "notes": ""}]
    cutting_capabilities = Column(JSON, default=list)   # [{"tool": "hand plasma", "cnc": false, "notes": ""}]
    forming_equipment = Column(JSON, default=list)      # [{"tool": "press brake", "specs": "60 ton, 6ft bed", "notes": ""}]
    finishing_capabilities = Column(JSON, default=list)  # [{"method": "spray paint", "in_house": true}, {"method": "powder coat", "in_house": false}]
    # Free-text answers (preserved for re-interpretation)
    raw_welding_answer = Column(Text, nullable=True)
    raw_forming_answer = Column(Text, nullable=True)
    raw_finishing_answer = Column(Text, nullable=True)
    shop_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="shop_equipment")


class MaterialPrice(Base):
    __tablename__ = "material_prices"

    id = Column(Integer, primary_key=True, index=True)
    material_type = Column(Enum(MaterialType), unique=True, nullable=False)
    price_per_lb = Column(Float)
    price_per_sqft = Column(Float)
    price_per_foot = Column(Float)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = Column(String)
