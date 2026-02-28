"""
Calculator registry — maps job_type strings to calculator classes.

Session 3 covers Priority A (5 types).
Session 3B adds the remaining 20 types (all 25 total).
"""

from .cantilever_gate import CantileverGateCalculator
from .swing_gate import SwingGateCalculator
from .straight_railing import StraightRailingCalculator
from .stair_railing import StairRailingCalculator
from .repair_decorative import RepairDecorativeCalculator
from .ornamental_fence import OrnamentalFenceCalculator
from .complete_stair import CompleteStairCalculator
from .spiral_stair import SpiralStairCalculator
from .window_security_grate import WindowSecurityGrateCalculator
from .balcony_railing import BalconyRailingCalculator
from .furniture_table import FurnitureTableCalculator
from .utility_enclosure import UtilityEnclosureCalculator
from .bollard import BollardCalculator
from .repair_structural import RepairStructuralCalculator
from .custom_fab import CustomFabCalculator
from .offroad_bumper import OffroadBumperCalculator
from .rock_slider import RockSliderCalculator
from .roll_cage import RollCageCalculator
from .exhaust_custom import ExhaustCustomCalculator
from .trailer_fab import TrailerFabCalculator
from .structural_frame import StructuralFrameCalculator
from .furniture_other import FurnitureOtherCalculator
from .sign_frame import SignFrameCalculator
from .led_sign_custom import LedSignCustomCalculator
from .product_firetable import ProductFiretableCalculator
from .base import BaseCalculator

CALCULATOR_REGISTRY = {
    # Priority A — gates & railings
    "cantilever_gate": CantileverGateCalculator,
    "swing_gate": SwingGateCalculator,
    "straight_railing": StraightRailingCalculator,
    "stair_railing": StairRailingCalculator,
    "repair_decorative": RepairDecorativeCalculator,
    # Priority B — structural & architectural
    "ornamental_fence": OrnamentalFenceCalculator,
    "complete_stair": CompleteStairCalculator,
    "spiral_stair": SpiralStairCalculator,
    "window_security_grate": WindowSecurityGrateCalculator,
    "balcony_railing": BalconyRailingCalculator,
    # Priority C — specialty
    "furniture_table": FurnitureTableCalculator,
    "utility_enclosure": UtilityEnclosureCalculator,
    "bollard": BollardCalculator,
    "repair_structural": RepairStructuralCalculator,
    "custom_fab": CustomFabCalculator,
    # Priority D — automotive
    "offroad_bumper": OffroadBumperCalculator,
    "rock_slider": RockSliderCalculator,
    "roll_cage": RollCageCalculator,
    "exhaust_custom": ExhaustCustomCalculator,
    # Priority E — industrial & signage
    "trailer_fab": TrailerFabCalculator,
    "structural_frame": StructuralFrameCalculator,
    "furniture_other": FurnitureOtherCalculator,
    "sign_frame": SignFrameCalculator,
    "led_sign_custom": LedSignCustomCalculator,
    # Priority F — products
    "product_firetable": ProductFiretableCalculator,
}


def get_calculator(job_type: str) -> BaseCalculator:
    """
    Returns an instance of the calculator for a job type.
    Falls back to CustomFabCalculator for unknown types instead of raising.
    """
    calc_class = CALCULATOR_REGISTRY.get(job_type, CustomFabCalculator)
    return calc_class()


def has_calculator(job_type: str) -> bool:
    """Check if a calculator exists for a job type."""
    return job_type in CALCULATOR_REGISTRY


def list_calculators() -> list:
    """List all registered calculator job types."""
    return list(CALCULATOR_REGISTRY.keys())
