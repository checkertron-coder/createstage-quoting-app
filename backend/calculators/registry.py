"""
Calculator registry — maps job_type strings to calculator classes.

Session 3 covers Priority A (5 types).
Future sessions will add the remaining 10.
"""

from .cantilever_gate import CantileverGateCalculator
from .swing_gate import SwingGateCalculator
from .straight_railing import StraightRailingCalculator
from .stair_railing import StairRailingCalculator
from .repair_decorative import RepairDecorativeCalculator
from .base import BaseCalculator

CALCULATOR_REGISTRY: dict[str, type] = {
    "cantilever_gate": CantileverGateCalculator,
    "swing_gate": SwingGateCalculator,
    "straight_railing": StraightRailingCalculator,
    "stair_railing": StairRailingCalculator,
    "repair_decorative": RepairDecorativeCalculator,
    # Session 3B or later: remaining 10 job types
}


def get_calculator(job_type: str) -> BaseCalculator:
    """Returns an instance of the calculator for a job type, or raises ValueError."""
    if job_type not in CALCULATOR_REGISTRY:
        raise ValueError(
            f"No calculator registered for job type: {job_type}. "
            f"Available: {list(CALCULATOR_REGISTRY.keys())}"
        )
    return CALCULATOR_REGISTRY[job_type]()


def has_calculator(job_type: str) -> bool:
    """Check if a calculator exists for a job type."""
    return job_type in CALCULATOR_REGISTRY


def list_calculators() -> list[str]:
    """List all registered calculator job types."""
    return list(CALCULATOR_REGISTRY.keys())
