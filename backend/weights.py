# Metal weight constants — source: AISC Steel Construction Manual + real Osario/Wexler quotes

# Densities (lb/in³)
DENSITIES = {
    "mild_steel": 0.2833,
    "stainless_304": 0.2890,
    "stainless_316": 0.2890,
    "aluminum_6061": 0.0975,
    "aluminum_5052": 0.0970,
    "dom_tubing": 0.2833,
    "square_tubing": 0.2833,
    "angle_iron": 0.2833,
    "flat_bar": 0.2833,
    "plate": 0.2833,
}

# Standard stock weights (lb/ft) for common shapes
# Verified against Osario & Wexler quotes (Chicago, 2023-2025)
STOCK_WEIGHTS = {
    # HR A500 Square Tubing — lb/ft
    "sq_tube_1x1_11ga": 0.857,
    "sq_tube_1x1_16ga": 0.581,
    "sq_tube_1.25x1.25_11ga": 1.147,
    "sq_tube_1.5x1.5_11ga": 1.403,
    "sq_tube_1.5x1.5_16ga": 0.960,
    "sq_tube_2x2_11ga": 1.951,
    "sq_tube_2x2_16ga": 1.316,
    "sq_tube_2.5x2.5_11ga": 2.495,
    "sq_tube_3x3_11ga": 3.090,
    "sq_tube_4x4_11ga": 4.180,
    # HR A500 Rectangular Tubing — lb/ft
    "rect_tube_4x2_11ga": 2.799,
    "rect_tube_3x2_11ga": 2.150,
    "rect_tube_3x1.5_11ga": 1.840,
    "rect_tube_2x1_11ga": 1.140,
    # A36 Flat Bar — lb/ft
    "flat_bar_0.1875x1.5": 0.956,
    "flat_bar_0.1875x2": 1.275,
    "flat_bar_0.1875x3": 1.913,
    "flat_bar_0.25x2": 1.701,
    "flat_bar_0.25x3": 2.550,
    "flat_bar_0.25x4": 3.400,
    "flat_bar_0.25x5": 4.253,
    "flat_bar_0.375x3": 3.826,
    "flat_bar_0.5x2": 3.400,
    "flat_bar_0.5x4": 6.800,
    "flat_bar_0.5x6": 10.200,
    # A36 Angle Iron — lb/ft
    "angle_1.5x1.5x0.125": 1.230,
    "angle_2x2x0.1875": 2.440,
    "angle_2x2x0.25": 3.190,
    "angle_3x3x0.25": 4.900,
    "angle_3x3x0.375": 7.200,
    "angle_4x4x0.25": 6.600,
    # A36 Channel — lb/ft
    "channel_3x4.1": 4.100,
    "channel_4x5.4": 5.400,
    "channel_6x8.2": 8.200,
    # DOM Round Tube (mechanical) — lb/ft
    "dom_round_1od_0.125wall": 1.028,
    "dom_round_1.5od_11ga": 1.769,
    "dom_round_1.5od_0.125wall": 1.611,
    "dom_round_2od_0.125wall": 2.194,
}

# Gauge to thickness conversion (inches)
GAUGE_TO_INCHES = {
    "10ga": 0.1345,
    "11ga": 0.1196,
    "12ga": 0.1046,
    "14ga": 0.0747,
    "16ga": 0.0598,
    "18ga": 0.0478,
    "20ga": 0.0359,
}


def weight_from_dimensions(
    length_in: float,
    width_in: float,
    thickness_in: float,
    material_type: str = "mild_steel"
) -> float:
    """
    Calculate weight in lbs from solid rectangular dimensions (inches).
    Use for plate, flat bar, sheet metal.
    For tubing/angle, use STOCK_WEIGHTS lookup instead.
    """
    density = DENSITIES.get(material_type, 0.2833)
    volume_in3 = length_in * width_in * thickness_in
    return round(volume_in3 * density, 3)


def weight_from_stock(stock_key: str, length_ft: float) -> float:
    """
    Calculate weight from standard stock shape and length in feet.
    Uses STOCK_WEIGHTS lookup table.
    """
    lb_per_ft = STOCK_WEIGHTS.get(stock_key, 0)
    return round(lb_per_ft * length_ft, 3)


def sqft_from_dimensions(length_in: float, width_in: float) -> float:
    """Calculate square footage from dimensions in inches. Used for powder coat."""
    return round((length_in * width_in) / 144.0, 3)


def gauge_to_thickness(gauge: str) -> float:
    """Convert gauge string (e.g. '11ga') to thickness in inches."""
    return GAUGE_TO_INCHES.get(gauge, 0)


def material_cost_from_weight(weight_lbs: float, price_per_lb: float, waste_factor: float = 0.05) -> float:
    """Calculate material cost with waste factor applied."""
    return round(weight_lbs * price_per_lb * (1 + waste_factor), 2)
