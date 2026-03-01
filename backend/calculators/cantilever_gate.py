"""
Cantilever gate material calculator.

Key geometry: A cantilever gate needs a counterbalance tail that extends
50-60% of the clear width behind the lead post. This is the #1 thing
people forget, and underquoting the tail is the #1 cantilever gate error.

The gate rides on roller carriages mounted to posts. The bottom rail
sits in a guide that keeps the gate aligned.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()

# Frame profile mapping from question tree answers to weights.py keys
FRAME_PROFILES = {
    ("2\" x 2\"", "11 gauge"): ("sq_tube_2x2_11ga", "sq_tube_2x2_11ga"),
    ("2\" x 2\"", "14 gauge"): ("sq_tube_2x2_14ga", "sq_tube_2x2_14ga"),
    ("2\" x 2\"", "16 gauge"): ("sq_tube_2x2_16ga", "sq_tube_2x2_16ga"),
    ("2\" x 3\"", "11 gauge"): ("rect_tube_2x3_11ga", "rect_tube_2x3_11ga"),
    ("2\" x 4\"", "11 gauge"): ("rect_tube_2x4_11ga", "rect_tube_2x4_11ga"),
    ("3\" x 3\"", "11 gauge"): ("sq_tube_3x3_11ga", "sq_tube_3x3_11ga"),
    ("4\" x 4\"", "11 gauge"): ("sq_tube_4x4_11ga", "sq_tube_4x4_11ga"),
    ("1-1/2\" x 1-1/2\"", "11 gauge"): ("sq_tube_1.5x1.5_11ga", "sq_tube_1.5x1.5_11ga"),
}

POST_PROFILES = {
    "4\" x 4\" square tube": ("sq_tube_4x4_11ga", "sq_tube_4x4_11ga"),
    "6\" x 6\" square tube": ("sq_tube_4x4_11ga", "sq_tube_4x4_11ga"),  # No 6x6 in weights, use 4x4 as proxy
    "4\" round pipe Sch 40": ("pipe_4_sch40", "pipe_4_sch40"),
    "6\" round pipe Sch 40": ("pipe_6_sch40", "pipe_6_sch40"),
}

INFILL_PROFILES = {
    "Pickets (vertical bars)": "sq_bar_0.75",
    "Flat bar vertical": "flat_bar_1x0.25",
    "Horizontal bars": "sq_bar_0.75",
}


class CantileverGateCalculator(BaseCalculator):

    TAIL_RATIO = 0.55  # Counterbalance tail = 55% of clear width (middle of 50-60%)

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list for custom/complex designs
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("cantilever_gate", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("cantilever_gate", ai_cuts, fields, assumptions)

        # --- Parse inputs ---
        clear_width_ft = self.parse_feet(fields.get("clear_width"), default=10.0)
        height_ft = self.parse_feet(fields.get("height"), default=6.0)
        clear_width_in = self.feet_to_inches(clear_width_ft)
        height_in = self.feet_to_inches(height_ft)

        frame_size = fields.get("frame_size", "2\" x 2\"")
        frame_gauge_raw = fields.get("frame_gauge", "11 gauge (0.120\" - standard for gates)")
        frame_gauge = self._normalize_gauge(frame_gauge_raw)

        post_size = fields.get("post_size", "4\" x 4\" square tube")
        post_count = self._parse_post_count(fields.get("post_count", "3 posts (standard)"))
        post_concrete_depth_in = 42.0  # Default 42" for Chicago area frost line
        if "Yes" in fields.get("post_concrete", "Yes"):
            post_concrete_depth_in = 42.0
        elif "No" in fields.get("post_concrete", ""):
            post_concrete_depth_in = 0.0

        infill_type = fields.get("infill_type", "Expanded metal")
        infill_spacing_in = self._parse_spacing(fields.get("picket_spacing",
                                                           fields.get("flat_bar_spacing", "4\" on-center")))

        has_motor = "Yes" in fields.get("has_motor", "No")
        motor_brand = fields.get("motor_brand", "")

        latch_type = fields.get("latch_lock", "Gravity latch")

        roller_type = fields.get("roller_carriages", "Standard duty (gates under 1,000 lbs)")

        finish = fields.get("finish", "Powder coat")

        # --- Geometry calculations ---
        tail_length_in = clear_width_in * self.TAIL_RATIO
        total_gate_length_in = clear_width_in + tail_length_in

        # Frame profile lookup
        frame_key = self._lookup_frame(frame_size, frame_gauge)
        frame_price_ft = lookup.get_price_per_foot(frame_key)

        # 1. Gate frame — outer perimeter (face + tail as one continuous frame)
        # Top rail: full gate length
        top_rail_in = total_gate_length_in
        # Bottom rail: full gate length
        bottom_rail_in = total_gate_length_in
        # Verticals: left end + right end + divider between face and tail
        left_vertical_in = height_in
        right_vertical_in = height_in
        divider_vertical_in = height_in  # Where face meets tail

        frame_total_in = top_rail_in + bottom_rail_in + left_vertical_in + right_vertical_in + divider_vertical_in
        frame_total_ft = self.inches_to_feet(frame_total_in)
        frame_pieces = self.apply_waste(self.linear_feet_to_pieces(frame_total_ft), self.WASTE_TUBE)
        frame_weight = self.get_weight_lbs(frame_key, frame_total_ft)
        frame_cost = round(frame_total_ft * frame_price_ft, 2)

        items.append(self.make_material_item(
            description=f"Gate frame — {frame_size} {frame_gauge} (face + counterbalance tail)",
            material_type="square_tubing",
            profile=frame_key,
            length_inches=frame_total_in,
            quantity=frame_pieces,
            unit_price=round(frame_total_ft * frame_price_ft / max(frame_pieces, 1), 2),
            cut_type="miter_45",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += frame_weight

        # Weld: 4 corners × tube height + 1 divider × 2 welds
        frame_weld = self.weld_inches_for_joints(10, avg_weld_length_in=frame_total_in / 80)
        total_weld_inches += 4 * height_in * 0.25 + 2 * height_in * 0.25  # Both sides of each vertical

        # 2. Internal mid-rails (horizontal stiffeners)
        mid_rail_count = 1 if height_in <= 72 else 2
        mid_rail_in = total_gate_length_in * mid_rail_count
        mid_rail_ft = self.inches_to_feet(mid_rail_in)
        mid_rail_weight = self.get_weight_lbs(frame_key, mid_rail_ft)

        items.append(self.make_material_item(
            description=f"Mid-rail stiffeners — {frame_size} {frame_gauge} × {mid_rail_count}",
            material_type="square_tubing",
            profile=frame_key,
            length_inches=mid_rail_in,
            quantity=self.linear_feet_to_pieces(mid_rail_ft),
            unit_price=round(mid_rail_ft * frame_price_ft / max(self.linear_feet_to_pieces(mid_rail_ft), 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += mid_rail_weight
        total_weld_inches += self.weld_inches_for_joints(mid_rail_count * 4, 3.0)

        # 3. Infill material — only on the gate face, not the tail
        face_width_in = clear_width_in
        face_height_in = height_in

        if "Expanded metal" in infill_type:
            infill_sqft = self.sq_ft_from_dimensions(face_width_in, face_height_in)
            infill_sheets = self.apply_waste(math.ceil(infill_sqft / 32.0), self.WASTE_SHEET)  # 4x8 = 32 sqft
            sheet_price = lookup.get_price_per_sqft("expanded_metal_13ga")
            infill_weight = self.get_plate_weight_lbs(face_width_in, face_height_in, 0.075)  # ~13ga

            items.append(self.make_material_item(
                description="Expanded metal infill — 13ga (gate face only)",
                material_type="plate",
                profile="expanded_metal_13ga",
                length_inches=face_width_in,
                quantity=infill_sheets,
                unit_price=round(32.0 * sheet_price, 2),  # Per sheet
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += infill_weight
            total_weld_inches += self.perimeter_inches(face_width_in, face_height_in) * 0.5  # Tack-welded perimeter

        elif "Pickets" in infill_type or "Flat bar" in infill_type:
            picket_profile = INFILL_PROFILES.get(infill_type, "sq_bar_0.75")
            picket_price_ft = lookup.get_price_per_foot(picket_profile)
            picket_count = math.ceil(face_width_in / infill_spacing_in) + 1
            picket_length_in = face_height_in - 2  # Minus top and bottom rail
            picket_total_ft = self.inches_to_feet(picket_length_in * picket_count)
            picket_weight = self.get_weight_lbs(picket_profile, picket_total_ft)

            items.append(self.make_material_item(
                description=f"Infill — {infill_type} at {infill_spacing_in}\" OC × {picket_count} pcs",
                material_type="flat_bar" if "Flat" in infill_type else "square_tubing",
                profile=picket_profile,
                length_inches=picket_length_in,
                quantity=self.apply_waste(picket_count, self.WASTE_FLAT if "Flat" in infill_type else self.WASTE_TUBE),
                unit_price=round(self.inches_to_feet(picket_length_in) * picket_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_FLAT if "Flat" in infill_type else self.WASTE_TUBE,
            ))
            total_weight += picket_weight
            total_weld_inches += self.weld_inches_for_joints(picket_count * 2, 1.5)  # Top and bottom tacks

        elif "Solid" in infill_type:
            infill_sqft = self.sq_ft_from_dimensions(face_width_in, face_height_in)
            infill_sheets = self.apply_waste(math.ceil(infill_sqft / 32.0), self.WASTE_SHEET)
            sheet_price = lookup.get_price_per_sqft("sheet_14ga")
            infill_weight = self.get_plate_weight_lbs(face_width_in, face_height_in, 0.075)

            items.append(self.make_material_item(
                description="Solid sheet panel infill — 14ga (gate face only)",
                material_type="plate",
                profile="sheet_14ga",
                length_inches=face_width_in,
                quantity=infill_sheets,
                unit_price=round(32.0 * sheet_price, 2),
                cut_type="square",
                waste_factor=self.WASTE_SHEET,
            ))
            total_weight += infill_weight
            total_weld_inches += self.perimeter_inches(face_width_in, face_height_in) * 0.5

        elif "Horizontal" in infill_type:
            bar_profile = INFILL_PROFILES.get(infill_type, "sq_bar_0.75")
            bar_price_ft = lookup.get_price_per_foot(bar_profile)
            bar_count = math.ceil(face_height_in / infill_spacing_in) + 1
            bar_length_in = face_width_in
            bar_total_ft = self.inches_to_feet(bar_length_in * bar_count)
            bar_weight = self.get_weight_lbs(bar_profile, bar_total_ft)

            items.append(self.make_material_item(
                description=f"Horizontal bar infill at {infill_spacing_in}\" OC × {bar_count} pcs",
                material_type="square_tubing",
                profile=bar_profile,
                length_inches=bar_length_in,
                quantity=self.apply_waste(bar_count, self.WASTE_TUBE),
                unit_price=round(self.inches_to_feet(bar_length_in) * bar_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += bar_weight
            total_weld_inches += self.weld_inches_for_joints(bar_count * 2, 2.0)

        # 4. Posts
        post_profile_key = self._lookup_post(post_size)
        post_price_ft = lookup.get_price_per_foot(post_profile_key)
        above_grade_in = height_in + 2  # 2" clearance above gate
        post_total_length_in = above_grade_in + post_concrete_depth_in
        post_total_ft = self.inches_to_feet(post_total_length_in) * post_count
        post_weight = self.get_weight_lbs(post_profile_key, post_total_ft)

        items.append(self.make_material_item(
            description=f"Posts — {post_size} × {post_count} ({self.inches_to_feet(post_total_length_in):.1f} ft each, includes {post_concrete_depth_in}\" embed)",
            material_type="square_tubing",
            profile=post_profile_key,
            length_inches=post_total_length_in,
            quantity=post_count,
            unit_price=round(self.inches_to_feet(post_total_length_in) * post_price_ft, 2),
            cut_type="square",
            waste_factor=0.0,
        ))
        total_weight += post_weight

        # 5. Post concrete
        if post_concrete_depth_in > 0:
            hole_diameter_in = 12.0  # Standard 12" diameter hole
            cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_concrete_depth_in
            total_cu_in = cu_in_per_hole * post_count
            total_cu_yd = total_cu_in / 46656.0  # 46656 cu in per cu yd
            concrete_price = lookup.get_unit_price("concrete_per_cuyd")

            items.append(self.make_material_item(
                description=f"Post concrete — {post_count} holes × 12\" dia × {post_concrete_depth_in}\" deep ({total_cu_yd:.2f} cu yd)",
                material_type="concrete",
                profile="concrete_footing",
                length_inches=post_concrete_depth_in,
                quantity=post_count,
                unit_price=round(total_cu_yd * concrete_price / post_count, 2),
                cut_type="n/a",
                waste_factor=0.0,
            ))
            assumptions.append(f"Post concrete: {total_cu_yd:.2f} cu yd based on {post_count} holes × 12\" diameter × {post_concrete_depth_in}\" deep.")

        # 6. Bottom guide rail
        guide_rail_in = total_gate_length_in + 24  # Extra 24" for approach
        guide_rail_ft = self.inches_to_feet(guide_rail_in)
        guide_price_ft = lookup.get_price_per_foot("angle_2x2x0.25")
        guide_weight = self.get_weight_lbs("angle_2x2x0.25", guide_rail_ft)

        items.append(self.make_material_item(
            description=f"Bottom guide rail — 2\"×2\"×1/4\" angle ({guide_rail_ft:.1f} ft)",
            material_type="angle_iron",
            profile="angle_2x2x0.25",
            length_inches=guide_rail_in,
            quantity=self.linear_feet_to_pieces(guide_rail_ft),
            unit_price=round(guide_rail_ft * guide_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += guide_weight

        # 7. Roller carriages (hardware)
        carriage_count = 2  # Standard: 2 carriages on 2 rear posts
        if "Heavy" in roller_type or "heavy" in roller_type:
            carriage_key = "roller_carriage_heavy"
        else:
            carriage_key = "roller_carriage_standard"

        hardware.append(self.make_hardware_item(
            description=f"Roller carriage — {'heavy duty' if 'heavy' in carriage_key else 'standard'}",
            quantity=carriage_count,
            options=lookup.get_hardware_options(carriage_key),
        ))

        # 8. Gate stops/bumpers
        hardware.append(self.make_hardware_item(
            description="Gate stop/bumper",
            quantity=2,
            options=lookup.get_hardware_options("gate_stop"),
        ))

        # 9. Motor (if applicable)
        if has_motor:
            motor_key = self._lookup_motor(motor_brand)
            hardware.append(self.make_hardware_item(
                description=f"Gate operator — {motor_brand or 'LiftMaster LA412'}",
                quantity=1,
                options=lookup.get_hardware_options(motor_key),
            ))

        # 10. Latch
        latch_key = self._lookup_latch(latch_type)
        if latch_key:
            hardware.append(self.make_hardware_item(
                description=f"Gate latch — {latch_type}",
                quantity=1,
                options=lookup.get_hardware_options(latch_key),
            ))

        # 11. Square footage for finishing
        # Both sides of gate face + posts (approximate)
        face_sqft = self.sq_ft_from_dimensions(clear_width_in, height_in) * 2  # Both sides
        tail_sqft = self.sq_ft_from_dimensions(tail_length_in, height_in) * 2
        post_sqft = post_count * self.sq_ft_from_dimensions(
            max(4, 4) * 4,  # Approximate post perimeter × length
            self.inches_to_feet(above_grade_in) * 12
        ) * 0.1  # Rough post area factor
        total_sq_ft = face_sqft + tail_sqft + post_sqft

        # 12. Total weld inches (add post-to-frame brackets etc.)
        total_weld_inches += self.weld_inches_for_joints(post_count * 2, 4.0)  # Post brackets

        # Assumptions
        assumptions.append(f"Counterbalance tail: {self.inches_to_feet(tail_length_in):.1f} ft ({self.TAIL_RATIO*100:.0f}% of {clear_width_ft:.0f} ft opening).")
        assumptions.append(f"Gate total length: {self.inches_to_feet(total_gate_length_in):.1f} ft (face + tail).")
        if not has_motor:
            assumptions.append("No gate operator included — manual operation.")

        return self.make_material_list(
            job_type="cantilever_gate",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    # --- Private helpers ---

    def _normalize_gauge(self, gauge_str: str) -> str:
        """Extract gauge label like '11 gauge' from answer string."""
        if "11" in gauge_str:
            return "11 gauge"
        elif "14" in gauge_str:
            return "14 gauge"
        elif "16" in gauge_str:
            return "16 gauge"
        elif "7" in gauge_str:
            return "7 gauge"
        return "11 gauge"

    def _lookup_frame(self, frame_size: str, frame_gauge: str) -> str:
        """Map question tree frame answers to weights.py / price lookup key."""
        key = (frame_size, frame_gauge)
        if key in FRAME_PROFILES:
            return FRAME_PROFILES[key][0]
        # Default fallback
        return "sq_tube_2x2_11ga"

    def _lookup_post(self, post_size: str) -> str:
        """Map post size answer to price/weight key."""
        if post_size in POST_PROFILES:
            return POST_PROFILES[post_size][0]
        return "sq_tube_4x4_11ga"

    def _parse_post_count(self, post_str: str) -> int:
        """Extract post count from answer string."""
        if "2" in post_str:
            return 2
        if "4" in post_str:
            return 4
        return 3  # Default

    def _parse_spacing(self, spacing_str: str) -> float:
        """Extract numeric spacing from answer string like '4\" on-center'."""
        if not spacing_str:
            return 4.0
        s = str(spacing_str)
        if "3.5" in s or "3-1/2" in s:
            return 3.5
        if "3" in s:
            return 3.0
        if "5" in s:
            return 5.0
        if "6" in s:
            return 6.0
        return 4.0

    def _lookup_motor(self, brand: str) -> str:
        """Map motor brand answer to hardware catalog key."""
        brand = str(brand).lower()
        if "la412" in brand or "liftmaster" in brand.lower():
            return "liftmaster_la412"
        if "patriot" in brand or "us automatic" in brand:
            return "us_automatic_patriot"
        return "liftmaster_la412"  # Default

    def _lookup_latch(self, latch_str: str) -> str:
        """Map latch answer to hardware catalog key."""
        if not latch_str or "None" in latch_str:
            return ""
        latch = str(latch_str).lower()
        if "gravity" in latch:
            return "gravity_latch"
        if "magnetic" in latch:
            return "magnetic_latch"
        if "deadbolt" in latch or "keyed" in latch:
            return "keyed_deadbolt"
        if "electric" in latch:
            return "electric_strike"
        return "gravity_latch"
