"""
Hardware Mapper — maps question tree answers to hardware catalog items.

Most calculators return empty hardware lists because only swing_gate and
cantilever_gate have hand-coded hardware logic. This mapper provides a
fallback: given a job_type and the user's answered fields, it returns
the appropriate HardwareItem dicts by looking up the HARDWARE_MAP.

Usage:
    from .hardware_mapper import map_hardware
    hw = map_hardware("straight_railing", fields)
"""

import logging
from typing import List

from .material_lookup import MaterialLookup, HARDWARE_CATALOG

logger = logging.getLogger(__name__)

_lookup = MaterialLookup()

# Gate operator mapping from motor_brand field values
_MOTOR_MAP = {
    "liftmaster": "liftmaster_la412",
    "la412": "liftmaster_la412",
    "us automatic": "us_automatic_patriot",
    "patriot": "us_automatic_patriot",
    "rsw12u": "liftmaster_rsw12u",
    "csw24u": "liftmaster_csw24u",
}

# Maps job_type -> field-based hardware rules.
# Special keys:
#   "_always" -> list of hardware_keys always included for this job type
#   field_id -> {answer_value: hardware_key} or {answer_value: "_motor_lookup"}
HARDWARE_MAP = {
    "swing_gate": {
        "hinge_type": {
            "Heavy duty": "heavy_duty_weld_hinge_pair",
            "Standard": "standard_weld_hinge_pair",
            "Ball bearing": "ball_bearing_hinge_pair",
        },
        "latch_type": {
            "Gravity": "gravity_latch",
            "Magnetic": "magnetic_latch",
            "Keyed deadbolt": "keyed_deadbolt",
            "Pool code": "pool_code_latch",
            "Electric strike": "electric_strike",
        },
        "has_motor": {"Yes": "_motor_lookup"},
        "auto_close": {
            "Spring hinge": "spring_hinge_pair",
            "Hydraulic closer": "hydraulic_closer",
        },
        "_always": ["gate_stop"],
    },
    "cantilever_gate": {
        "has_motor": {"Yes": "_motor_lookup"},
        "_always": ["roller_carriage_standard", "gate_stop"],
    },
    "straight_railing": {
        "_always": ["surface_mount_flange"],
    },
    "stair_railing": {
        "_always": ["surface_mount_flange"],
    },
    "balcony_railing": {
        "_always": ["surface_mount_flange"],
    },
    "complete_stair": {
        "_always": ["surface_mount_flange"],
    },
    "spiral_stair": {
        "_always": ["surface_mount_flange"],
    },
    "bollard": {
        "mount_type": {
            "Surface mount": "anchor_bolt_set",
            "Surface": "anchor_bolt_set",
        },
    },
    "ornamental_fence": {
        "_always": ["gate_stop"],
    },
    "window_security_grate": {},
}


def _resolve_motor(fields):
    """Look up the motor hardware key from fields."""
    brand = str(fields.get("motor_brand", "") or "").lower().strip()
    for keyword, hw_key in _MOTOR_MAP.items():
        if keyword in brand:
            return hw_key
    # Default motor if brand not recognized
    return "liftmaster_la412"


def _make_hardware_item(hw_key, quantity=1):
    """Build a HardwareItem dict from a hardware catalog key."""
    entry = HARDWARE_CATALOG.get(hw_key)
    if not entry:
        return None
    description = hw_key.replace("_", " ").title()
    return {
        "description": description,
        "quantity": quantity,
        "options": entry["options"],
    }


def map_hardware(job_type, fields):
    """
    Map a job_type + answered fields to a list of HardwareItem dicts.

    Args:
        job_type: str, e.g. "straight_railing"
        fields: dict of answered question fields

    Returns:
        list of HardwareItem dicts (may be empty)
    """
    if not fields:
        fields = {}

    rules = HARDWARE_MAP.get(job_type, {})
    if not rules:
        return []

    hardware = []
    seen_keys = set()

    # Process "_always" items first
    for hw_key in rules.get("_always", []):
        if hw_key in seen_keys:
            continue
        # For mount flanges, estimate quantity from post count or linear footage
        quantity = 1
        if hw_key == "surface_mount_flange":
            post_count = _parse_int(fields.get("post_count", 0))
            if post_count > 0:
                quantity = post_count
            else:
                linear_ft = _parse_float(fields.get("linear_footage", 0))
                if linear_ft > 0:
                    # Roughly one flange per 4 feet of railing
                    quantity = max(2, int(linear_ft / 4) + 1)
                else:
                    quantity = 2  # minimum pair
        item = _make_hardware_item(hw_key, quantity)
        if item:
            hardware.append(item)
            seen_keys.add(hw_key)

    # Process field-based mappings
    for field_id, value_map in rules.items():
        if field_id.startswith("_"):
            continue  # skip "_always"
        answer = str(fields.get(field_id, "") or "").strip()
        if not answer:
            continue

        # Try exact match first, then case-insensitive partial
        hw_key = value_map.get(answer)
        if not hw_key:
            answer_lower = answer.lower()
            for val, key in value_map.items():
                if val.lower() in answer_lower or answer_lower in val.lower():
                    hw_key = key
                    break

        if not hw_key:
            continue

        if hw_key == "_motor_lookup":
            hw_key = _resolve_motor(fields)

        if hw_key in seen_keys:
            continue

        item = _make_hardware_item(hw_key)
        if item:
            hardware.append(item)
            seen_keys.add(hw_key)

    return hardware


def _parse_int(value):
    """Safe int parse."""
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _parse_float(value):
    """Safe float parse."""
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return 0.0
