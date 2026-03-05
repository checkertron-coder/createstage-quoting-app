"""
Cantilever gate material calculator.

Key geometry: A cantilever gate needs a counterbalance tail that extends
50-60% of the clear width behind the lead post. This is the #1 thing
people forget, and underquoting the tail is the #1 cantilever gate error.

The gate rides on roller carriages mounted to posts. The bottom rail
sits in a guide that keeps the gate aligned.
"""

import logging
import math
import re

from .base import BaseCalculator

logger = logging.getLogger(__name__)
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

# Picket material options from question tree → profile keys
PICKET_MATERIAL_PROFILES = {
    '1/2" square': "sq_bar_0.5",
    '5/8" square': "sq_bar_0.625",
    '3/4" square': "sq_bar_0.75",
    '1" square': "sq_bar_1.0",
    '5/8" round': "round_bar_0.625",
    '3/4" round': "round_bar_0.75",
    '1/2" round': "round_bar_0.5",
}


def _resolve_picket_profile(fields, infill_type):
    """Resolve picket profile from picket_material field, with fallback to INFILL_PROFILES.

    Handles variations from AI text extraction:
    - Exact substring match: '5/8" square' in picket_material
    - Fraction regex: extracts '5/8' from '5/8 inch square bar' etc.
    - Decimal form: '0.625' maps to 5/8", '0.5' maps to 1/2", '0.75' maps to 3/4"
    """
    picket_material = str(fields.get("picket_material", "")).lower().strip()
    if picket_material:
        # 1. Exact substring match (existing logic)
        for label, profile in PICKET_MATERIAL_PROFILES.items():
            if label.lower() in picket_material:
                return profile

        # 2. Fraction regex fallback: extract fractions like 5/8, 3/4, 1/2
        fraction_match = re.search(r'(\d+)/(\d+)', picket_material)
        if fraction_match:
            frac_str = fraction_match.group(0)  # e.g. "5/8"
            is_round = "round" in picket_material
            for label, profile in PICKET_MATERIAL_PROFILES.items():
                if frac_str in label:
                    if is_round and "round" in label:
                        return profile
                    elif not is_round and "square" in label:
                        return profile
            # If shape didn't match exactly, return first fraction match
            for label, profile in PICKET_MATERIAL_PROFILES.items():
                if frac_str in label:
                    return profile

        # 3. Decimal fallback: 0.625 → 5/8, 0.5 → 1/2, 0.75 → 3/4, 1.0 → 1"
        _DECIMAL_TO_FRACTION = {
            "0.5": '1/2"',
            "0.625": '5/8"',
            "0.75": '3/4"',
            "1.0": '1"',
        }
        decimal_match = re.search(r'(\d+\.\d+)', picket_material)
        if decimal_match:
            dec_str = decimal_match.group(1)
            frac_label = _DECIMAL_TO_FRACTION.get(dec_str, "")
            if frac_label:
                is_round = "round" in picket_material
                for label, profile in PICKET_MATERIAL_PROFILES.items():
                    if frac_label in label:
                        if is_round and "round" in label:
                            return profile
                        elif not is_round and "square" in label:
                            return profile
                # Fallback: return first match ignoring shape
                for label, profile in PICKET_MATERIAL_PROFILES.items():
                    if frac_label in label:
                        return profile

    # Fallback to old infill_type mapping
    return INFILL_PROFILES.get(infill_type, "sq_bar_0.75")


def _is_post_item(item):
    """Detect if an item is a gate/fence post by description keywords."""
    desc = item.get("description", "").lower()
    post_keywords = ["gate post", "hinge post", "latch post", "strike post",
                     "terminal post", "corner post", "end post", "line post"]
    return any(kw in desc for kw in post_keywords)


def _is_overhead_item(item):
    """Detect overhead beam by description keywords."""
    desc = item.get("description", "").lower()
    return any(kw in desc for kw in ["overhead", "support beam", "header beam",
                                      "track beam", "spanning beam"])


class CantileverGateCalculator(BaseCalculator):

    TAIL_RATIO = 0.55  # Counterbalance tail = 55% of clear width (middle of 50-60%)

    def calculate(self, fields: dict) -> dict:
        items = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # --- Parse inputs needed for hardware (before AI check) ---
        has_motor = "Yes" in fields.get("has_motor", "No")
        motor_brand = fields.get("motor_brand", "")
        latch_type = fields.get("latch_lock", "Gravity latch")
        roller_type = fields.get("roller_carriages", "Standard duty (gates under 1,000 lbs)")
        bottom_guide_type = fields.get("bottom_guide", "Surface mount guide roller")
        is_top_hung = (
            "No bottom guide" in bottom_guide_type
            or "top-hung" in bottom_guide_type.lower()
        )

        # --- Build hardware list BEFORE AI check (shared by both paths) ---
        hardware = self._build_hardware(
            has_motor, motor_brand, latch_type, roller_type, is_top_hung, fields)

        # Inject post profile key so AI knows the exact profile to use
        post_size = fields.get("post_size", "4\" x 4\" square tube")
        fields["_post_profile_key"] = self._lookup_post(post_size)

        # Try AI cut list for custom/complex designs
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("cantilever_gate", fields)
            if ai_cuts is not None:
                ai_result = self._build_from_ai_cuts(
                    "cantilever_gate", ai_cuts, fields, assumptions,
                    hardware=hardware)
                return self._post_process_ai_result(ai_result, fields, assumptions)

        # --- Parse remaining inputs ---
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
            picket_profile = _resolve_picket_profile(fields, infill_type)
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
            bar_profile = _resolve_picket_profile(fields, infill_type)
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

        # 6. Bottom guide rail — conditional on bottom_guide field
        if is_top_hung:
            # Top-hung / top-mount — no bottom guide, add overhead support beam
            # Gate weight estimation for beam sizing
            estimated_gate_weight = total_weight  # Weight so far (frame + infill)
            if estimated_gate_weight < 800:
                beam_profile = "hss_4x4_0.25"
                beam_desc = "HSS 4×4×1/4\""
            else:
                beam_profile = "hss_6x4_0.25"
                beam_desc = "HSS 6×4×1/4\""
            beam_length_in = total_gate_length_in + 24  # Span + 12" overhang each side
            beam_length_ft = self.inches_to_feet(beam_length_in)
            beam_price_ft = lookup.get_price_per_foot(beam_profile)
            beam_weight = self.get_weight_lbs(beam_profile, beam_length_ft)
            if beam_weight == 0.0:
                beam_weight = beam_length_ft * 12.0  # ~12 lbs/ft estimate for HSS

            items.append(self.make_material_item(
                description=f"Overhead support beam — {beam_desc} ({beam_length_ft:.1f} ft)",
                material_type="square_tubing",
                profile=beam_profile,
                length_inches=beam_length_in,
                quantity=self.linear_feet_to_pieces(beam_length_ft),
                unit_price=round(beam_length_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += beam_weight
            total_weld_inches += self.weld_inches_for_joints(4, 6.0)  # Beam-to-post welds
            min_clearance_in = height_in + 6
            assumptions.append(
                "Top-hung system — overhead %s beam supports top-mount roller carriages. "
                "Minimum overhead clearance: %d\" (%.1f ft)."
                % (beam_desc, int(min_clearance_in), self.inches_to_feet(min_clearance_in)))
        elif "Embedded" in bottom_guide_type:
            # Embedded track — use channel instead of angle
            guide_rail_in = total_gate_length_in + 24  # Extra 24" for approach
            guide_rail_ft = self.inches_to_feet(guide_rail_in)
            guide_profile = "channel_4x5.4"
            guide_price_ft = lookup.get_price_per_foot(guide_profile)
            guide_weight = self.get_weight_lbs(guide_profile, guide_rail_ft)

            items.append(self.make_material_item(
                description=f"Bottom guide — embedded C4×5.4 channel ({guide_rail_ft:.1f} ft)",
                material_type="channel",
                profile=guide_profile,
                length_inches=guide_rail_in,
                quantity=self.linear_feet_to_pieces(guide_rail_ft),
                unit_price=round(guide_rail_ft * guide_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += guide_weight
            assumptions.append("Embedded bottom guide: C4×5.4 channel flush-mounted in concrete.")
        else:
            # Surface mount (default) — angle iron guide rail
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

        # 7. Square footage for finishing
        # Both sides of gate face + posts (approximate)
        face_sqft = self.sq_ft_from_dimensions(clear_width_in, height_in) * 2  # Both sides
        tail_sqft = self.sq_ft_from_dimensions(tail_length_in, height_in) * 2
        post_sqft = post_count * self.sq_ft_from_dimensions(
            max(4, 4) * 4,  # Approximate post perimeter × length
            self.inches_to_feet(above_grade_in) * 12
        ) * 0.1  # Rough post area factor
        total_sq_ft = face_sqft + tail_sqft + post_sqft

        # 8. Total weld inches (add post-to-frame brackets etc.)
        total_weld_inches += self.weld_inches_for_joints(post_count * 2, 4.0)  # Post brackets

        # 9. Adjacent fence sections (compound job)
        adjacent_fence = fields.get("adjacent_fence", "No")
        if "Yes" in str(adjacent_fence):
            resolved_picket = _resolve_picket_profile(fields, infill_type)
            fence_result = self._generate_fence_sections(
                fields, height_in, infill_type, infill_spacing_in,
                frame_key, frame_size, frame_gauge, frame_price_ft,
                post_profile_key, post_price_ft, post_concrete_depth_in,
                gate_picket_profile=resolved_picket,
            )
            items.extend(fence_result["items"])
            hardware.extend(fence_result["hardware"])
            total_weight += fence_result["weight"]
            total_sq_ft += fence_result["sq_ft"]
            total_weld_inches += fence_result["weld_inches"]
            assumptions.extend(fence_result["assumptions"])

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

    def _post_process_ai_result(self, ai_result, fields, assumptions):
        """
        Lightweight safety net for AI-generated material lists.

        Philosophy: TRUST the AI output. The prompt has all the constraints
        (profile keys, dimensions, quantities). This method only:
        1. Adds items the AI completely omitted (concrete, overhead beam)
        2. Adds fence sections if AI missed them entirely
        3. Records assumptions for the quote document

        It does NOT re-count, re-profile, or re-size AI items.
        """
        items = list(ai_result.get("items", []))
        cut_list = list(ai_result.get("cut_list", []))

        # ========================================================
        # Remove bulk aggregate items — these are Claude's raw
        # material summaries (e.g. "sq_tube_2x2_11ga — 247.7 ft")
        # that get replaced by the itemized pieces below.
        # A bulk aggregate has qty=1 and description = "profile — X.X ft"
        # ========================================================
        items = [
            item for item in items
            if not (
                item.get("quantity", 0) == 1
                and " — " in item.get("description", "")
                and item.get("description", "").rstrip().endswith("ft")
            )
        ]

        # ========================================================
        # Build itemized material items from the cut list.
        # Each cut list entry becomes a material line item that a
        # fabricator can read: description, profile, length, qty, price.
        # ========================================================
        if cut_list:
            for cut in cut_list:
                profile = cut.get("profile", "")
                length_in = cut.get("length_inches", 0)
                quantity = cut.get("quantity", 1)
                if not profile or length_in <= 0:
                    continue
                length_ft = self.inches_to_feet(length_in)
                price_ft = lookup.get_price_per_foot(profile)
                if price_ft == 0.0:
                    price_ft = 3.50
                unit_price = round(length_ft * price_ft, 2)
                desc = cut.get("description", profile)
                items.append(self.make_material_item(
                    description=desc,
                    material_type=cut.get("material_type", "mild_steel"),
                    profile=profile,
                    length_inches=length_in,
                    quantity=quantity,
                    unit_price=unit_price,
                    cut_type=cut.get("cut_type", "square"),
                    waste_factor=0.0,
                ))

        # --- Parse fields ---
        clear_width_ft = self.parse_feet(fields.get("clear_width"), default=10.0)
        height_ft = self.parse_feet(fields.get("height"), default=6.0)

        # Sanity check: residential gates/fences are typically 3-12 ft.
        # If height exceeds 12 ft, it may be a parsing error (fence length
        # confused with gate height).
        if height_ft > 12.0:
            logger.warning(
                "Gate height %.1f ft seems too tall — may be a parsing error. "
                "height field = %r", height_ft, fields.get("height"))
            assumptions.append(
                "WARNING: Gate height %.1f ft exceeds typical residential range "
                "(3-12 ft). Verify the height field is correct." % height_ft)

        clear_width_in = self.feet_to_inches(clear_width_ft)
        height_in = self.feet_to_inches(height_ft)
        total_gate_length_in = clear_width_in * 1.5

        post_size = fields.get("post_size", "4\" x 4\" square tube")
        post_count = self._parse_post_count(fields.get("post_count", "3 posts (standard)"))
        post_profile_key = self._lookup_post(post_size)
        post_price_ft = lookup.get_price_per_foot(post_profile_key)
        post_concrete_depth_in = 42.0
        if "No" in str(fields.get("post_concrete", "Yes")):
            post_concrete_depth_in = 0.0

        above_grade_in = height_in + 2
        post_total_length_in = above_grade_in + post_concrete_depth_in

        bottom_guide_type = fields.get("bottom_guide", "Surface mount guide roller")
        is_top_hung = (
            "No bottom guide" in str(bottom_guide_type)
            or "top-hung" in str(bottom_guide_type).lower()
        )

        infill_type = fields.get("infill_type", "Pickets (vertical bars)")
        infill_spacing_in = self._parse_spacing(
            fields.get("picket_spacing",
                        fields.get("flat_bar_spacing", "4\" on-center")))

        frame_size = fields.get("frame_size", "2\" x 2\"")
        frame_gauge_raw = fields.get("frame_gauge", "11 gauge (0.120\" - standard for gates)")
        frame_gauge = self._normalize_gauge(frame_gauge_raw)
        frame_key = self._lookup_frame(frame_size, frame_gauge)
        frame_price_ft = lookup.get_price_per_foot(frame_key)

        total_weight = ai_result.get("total_weight_lbs", 0.0)
        total_sq_ft = ai_result.get("total_sq_ft", 0.0)
        total_weld_inches = ai_result.get("weld_linear_inches", 0.0)

        # ========================================================
        # SAFETY NET: Add posts only if AI completely omitted them
        # ========================================================
        has_gate_posts = any(
            _is_post_item(item)
            and "fence" not in item.get("description", "").lower()
            for item in items
        )
        if not has_gate_posts:
            post_total_ft = self.inches_to_feet(post_total_length_in) * post_count
            post_weight = self.get_weight_lbs(post_profile_key, post_total_ft)
            items.append(self.make_material_item(
                description="Gate posts — %d × %s (%.1f ft each, %.0f\" embed)"
                            % (post_count, post_size,
                               self.inches_to_feet(post_total_length_in),
                               post_concrete_depth_in),
                material_type="square_tubing",
                profile=post_profile_key,
                length_inches=post_total_length_in,
                quantity=post_count,
                unit_price=round(self.inches_to_feet(post_total_length_in)
                                 * post_price_ft, 2),
                cut_type="square",
                waste_factor=0.0,
            ))
            total_weight += post_weight

        # ========================================================
        # SAFETY NET: Add concrete only if AI completely omitted it
        # ========================================================
        has_concrete = any(
            "concrete" in item.get("description", "").lower()
            for item in items
        )
        if not has_concrete and post_concrete_depth_in > 0:
            hole_diameter_in = 12.0
            cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_concrete_depth_in
            total_cu_yd = (cu_in_per_hole * post_count) / 46656.0
            concrete_price = lookup.get_unit_price("concrete_per_cuyd")
            items.append(self.make_material_item(
                description="Post concrete — %d holes × 12\" dia × %.0f\" deep"
                            % (post_count, post_concrete_depth_in),
                material_type="concrete",
                profile="concrete_footing",
                length_inches=post_concrete_depth_in,
                quantity=post_count,
                unit_price=round(total_cu_yd * concrete_price / post_count, 2),
                cut_type="n/a",
                waste_factor=0.0,
            ))

        # ========================================================
        # SAFETY NET: Overhead beam — add if missing, enforce qty=1 + profile
        # ========================================================
        if is_top_hung:
            has_overhead = any(_is_overhead_item(item) for item in items)
            if not has_overhead:
                estimated_gate_weight = total_weight
                if estimated_gate_weight < 800:
                    beam_profile = "hss_4x4_0.25"
                    beam_desc = "HSS 4x4x1/4\""
                else:
                    beam_profile = "hss_6x4_0.25"
                    beam_desc = "HSS 6x4x1/4\""
                beam_length_in = total_gate_length_in + 24
                beam_length_ft = self.inches_to_feet(beam_length_in)
                beam_price_ft = lookup.get_price_per_foot(beam_profile)
                beam_weight = self.get_weight_lbs(beam_profile, beam_length_ft)
                if beam_weight == 0.0:
                    beam_weight = beam_length_ft * 12.0
                items.append(self.make_material_item(
                    description="Overhead support beam — %s (%.1f ft)"
                                % (beam_desc, beam_length_ft),
                    material_type="hss_structural_tube",
                    profile=beam_profile,
                    length_inches=beam_length_in,
                    quantity=1,
                    unit_price=round(beam_length_ft * beam_price_ft, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_TUBE,
                ))
                total_weight += beam_weight
            else:
                # AI included overhead beam — enforce qty=1 and validate profile
                estimated_gate_weight = total_weight
                if estimated_gate_weight < 800:
                    correct_profile = "hss_4x4_0.25"
                else:
                    correct_profile = "hss_6x4_0.25"
                for item in items:
                    if _is_overhead_item(item) or item.get("profile", "").startswith("hss_"):
                        if item.get("quantity", 1) > 1:
                            item["quantity"] = 1
                            item["line_total"] = round(item.get("unit_price", 0), 2)
                            assumptions.append(
                                "Overhead beam quantity corrected to 1 "
                                "(one beam spans full gate length).")
                        if item.get("profile", "") != correct_profile:
                            old_profile = item["profile"]
                            item["profile"] = correct_profile
                            beam_len_ft = self.inches_to_feet(
                                item.get("length_inches", total_gate_length_in + 24))
                            new_price = round(
                                beam_len_ft * lookup.get_price_per_foot(correct_profile), 2)
                            item["unit_price"] = new_price
                            item["line_total"] = round(new_price * item.get("quantity", 1), 2)
                            assumptions.append(
                                "Beam profile corrected: %s -> %s "
                                "(estimated gate weight %.0f lbs)."
                                % (old_profile, correct_profile, estimated_gate_weight))

                # Sync beam profile correction to cut_list entries
                for cl_entry in cut_list:
                    if _is_overhead_item(cl_entry) or cl_entry.get("profile", "").startswith("hss_"):
                        if cl_entry.get("quantity", 1) > 1:
                            cl_entry["quantity"] = 1
                        if cl_entry.get("profile", "") != correct_profile:
                            cl_entry["profile"] = correct_profile

        # ========================================================
        # SAFETY NET: Add fence sections only if AI completely omitted them
        # ========================================================
        adjacent_fence = fields.get("adjacent_fence", "No")
        if "Yes" in str(adjacent_fence):
            has_any_fence = any(
                "fence" in item.get("description", "").lower()
                for item in items
            )
            if not has_any_fence:
                resolved_picket = _resolve_picket_profile(fields, infill_type)
                fence_result = self._generate_fence_sections(
                    fields, height_in, infill_type, infill_spacing_in,
                    frame_key, frame_size, frame_gauge, frame_price_ft,
                    post_profile_key, post_price_ft, post_concrete_depth_in,
                    gate_picket_profile=resolved_picket,
                )
                items.extend(fence_result["items"])
                total_weight += fence_result["weight"]
                total_sq_ft += fence_result["sq_ft"]
                total_weld_inches += fence_result["weld_inches"]
                assumptions.extend(fence_result["assumptions"])

        # ========================================================
        # SAFETY NET: Validate gate picket count
        # ========================================================
        if "Picket" in str(infill_type) or "bar" in str(infill_type).lower():
            expected_picket_count = math.ceil(total_gate_length_in / infill_spacing_in) + 1
            for item in items:
                desc_lower = item.get("description", "").lower()
                if ("picket" in desc_lower or "infill" in desc_lower) \
                        and "fence" not in desc_lower:
                    actual_qty = item.get("quantity", 0)
                    if actual_qty < expected_picket_count * 0.8:
                        assumptions.append(
                            "WARNING: Gate picket count (%d) may be low. "
                            "Expected ~%d for %.0f\" panel at %.0f\" spacing."
                            % (actual_qty, expected_picket_count,
                               total_gate_length_in, infill_spacing_in))

        # ========================================================
        # Record assumptions (informational — no corrections)
        # ========================================================
        assumptions.append(
            "Cantilever gate panel: %.1f ft total (%.0f ft opening x 1.5). "
            "Tail: %.1f ft."
            % (self.inches_to_feet(total_gate_length_in), clear_width_ft,
               self.inches_to_feet(total_gate_length_in - clear_width_in)))
        assumptions.append(
            "Posts: %s, %.1f ft each (%.0f\" above grade + 2\" clearance "
            "+ %.0f\" embed)."
            % (post_size, self.inches_to_feet(post_total_length_in),
               height_in, post_concrete_depth_in))

        # Rebuild the result
        ai_result["items"] = items
        ai_result["cut_list"] = cut_list
        ai_result["total_weight_lbs"] = round(total_weight, 1)
        ai_result["total_sq_ft"] = round(total_sq_ft, 1)
        ai_result["weld_linear_inches"] = round(total_weld_inches, 1)
        ai_result["assumptions"] = assumptions
        return ai_result

    def _build_hardware(self, has_motor, motor_brand, latch_type, roller_type,
                        is_top_hung, fields):
        """
        Build the hardware list for the gate. Called BEFORE the AI check so
        hardware (with correct quantities) flows through both AI and rule-based paths.
        """
        hardware = []
        carriage_count = 2  # Standard: 2 carriages on 2 rear posts

        # Roller carriages
        if "Heavy" in str(roller_type) or "heavy" in str(roller_type):
            carriage_key = "roller_carriage_heavy"
        else:
            carriage_key = "roller_carriage_standard"

        carriage_desc = "Top-mount roller carriage" if is_top_hung else "Roller carriage"
        carriage_desc += " — %s" % ("heavy duty" if "heavy" in carriage_key else "standard")

        hardware.append(self.make_hardware_item(
            description=carriage_desc,
            quantity=carriage_count,
            options=lookup.get_hardware_options(carriage_key),
        ))

        # Gate stops/bumpers
        hardware.append(self.make_hardware_item(
            description="Gate stop/bumper",
            quantity=2,
            options=lookup.get_hardware_options("gate_stop"),
        ))

        # Motor (if applicable)
        if has_motor:
            motor_key = self._lookup_motor(motor_brand)
            hardware.append(self.make_hardware_item(
                description="Gate operator — %s" % (motor_brand or "LiftMaster LA412"),
                quantity=1,
                options=lookup.get_hardware_options(motor_key),
            ))

        # Latch
        latch_key = self._lookup_latch(latch_type)
        if latch_key:
            hardware.append(self.make_hardware_item(
                description="Gate latch — %s" % latch_type,
                quantity=1,
                options=lookup.get_hardware_options(latch_key),
            ))

        return hardware

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

    def _generate_fence_sections(self, fields, height_in, infill_type, infill_spacing_in,
                                    frame_key, frame_size, frame_gauge, frame_price_ft,
                                    post_profile_key, post_price_ft, post_concrete_depth_in,
                                    gate_picket_profile=None):
        """Generate material items for adjacent fence sections."""
        items = []
        hardware = []
        weight = 0.0
        sq_ft = 0.0
        weld_inches = 0.0
        assumptions = []

        side_1_ft = self.parse_feet(fields.get("fence_side_1_length"), default=0.0)
        side_2_ft = self.parse_feet(fields.get("fence_side_2_length"), default=0.0)
        # Use explicit post count if provided, otherwise estimate from spacing
        fence_post_count_raw = self.parse_int(fields.get("fence_post_count"), default=0)
        fence_match = fields.get("fence_infill_match", "Yes — match gate infill exactly")

        sides = []
        if side_1_ft > 0:
            sides.append(("Side 1", side_1_ft))
        if side_2_ft > 0:
            sides.append(("Side 2", side_2_ft))

        if not sides:
            return {"items": items, "hardware": hardware, "weight": weight,
                    "sq_ft": sq_ft, "weld_inches": weld_inches, "assumptions": assumptions}

        # Distribute explicit post count across sides, or estimate
        total_fence_ft = sum(l for _, l in sides)
        for side_name, length_ft in sides:
            length_in = self.feet_to_inches(length_ft)

            # Fence posts (line posts between gate post and termination)
            # Gate post is shared, so we only need intermediate + terminal posts
            if fence_post_count_raw > 0:
                # Distribute user-specified posts proportionally across sides
                side_fraction = length_ft / total_fence_ft if total_fence_ft > 0 else 0.5
                post_count = max(1, round(fence_post_count_raw * side_fraction))
            else:
                # Estimate: one post every 6-8 ft
                post_count = max(1, math.ceil(length_ft / 6.0))
            above_grade_in = height_in + 2
            post_total_length_in = above_grade_in + post_concrete_depth_in
            post_total_ft = self.inches_to_feet(post_total_length_in) * post_count
            post_weight = self.get_weight_lbs(post_profile_key, post_total_ft)

            items.append(self.make_material_item(
                description=f"Fence posts — {side_name} × {post_count} ({self.inches_to_feet(post_total_length_in):.1f} ft each)",
                material_type="square_tubing",
                profile=post_profile_key,
                length_inches=post_total_length_in,
                quantity=post_count,
                unit_price=round(self.inches_to_feet(post_total_length_in) * post_price_ft, 2),
                cut_type="square",
                waste_factor=0.0,
            ))
            weight += post_weight

            # Post concrete for fence posts
            if post_concrete_depth_in > 0:
                hole_diameter_in = 12.0
                cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_concrete_depth_in
                total_cu_in = cu_in_per_hole * post_count
                total_cu_yd = total_cu_in / 46656.0
                concrete_price = lookup.get_unit_price("concrete_per_cuyd")

                items.append(self.make_material_item(
                    description=f"Fence post concrete — {side_name} × {post_count} holes",
                    material_type="concrete",
                    profile="concrete_footing",
                    length_inches=post_concrete_depth_in,
                    quantity=post_count,
                    unit_price=round(total_cu_yd * concrete_price / post_count, 2),
                    cut_type="n/a",
                    waste_factor=0.0,
                ))

            # Fence rails — top and bottom rails spanning between posts
            # Number of panel spans = post_count (gate post to first, intermediate spans, to terminal)
            rail_count = 2  # top + bottom
            rail_total_in = length_in * rail_count
            rail_total_ft = self.inches_to_feet(rail_total_in)
            rail_weight = self.get_weight_lbs(frame_key, rail_total_ft)

            items.append(self.make_material_item(
                description=f"Fence rails — {side_name} top + bottom ({length_ft:.1f} ft each)",
                material_type="square_tubing",
                profile=frame_key,
                length_inches=length_in,
                quantity=self.apply_waste(self.linear_feet_to_pieces(rail_total_ft), self.WASTE_TUBE),
                unit_price=round(length_ft * frame_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            weight += rail_weight
            weld_inches += self.weld_inches_for_joints(post_count * rail_count * 2, 2.0)

            # Fence mid-rails (horizontal stiffeners for tall fence sections)
            fence_mid_rail_count = 0
            if height_in > 72:
                fence_mid_rail_count = 2
            elif height_in > 48:
                fence_mid_rail_count = 1

            if fence_mid_rail_count > 0:
                # Determine mid-rail profile based on mid_rail_type selection
                mr_profile = frame_key
                mr_price = frame_price_ft
                mr_label = "tube"
                mid_rail_type = fields.get("mid_rail_type", "")
                if "punched" in str(mid_rail_type).lower() or "pre-punched" in str(mid_rail_type).lower():
                    picket_profile = _resolve_picket_profile(fields, infill_type)
                    if "0.5" in picket_profile and "0.625" not in picket_profile:
                        mr_profile = "punched_channel_1.5x0.5_fits_0.5"
                    elif "0.625" in picket_profile:
                        mr_profile = "punched_channel_1.5x0.5_fits_0.625"
                    elif "0.75" in picket_profile:
                        mr_profile = "punched_channel_1.5x0.5_fits_0.75"
                    mr_price = lookup.get_price_per_foot(mr_profile)
                    mr_label = "pre-punched channel"

                mid_rail_total_in = length_in * fence_mid_rail_count
                mid_rail_total_ft = self.inches_to_feet(mid_rail_total_in)
                mid_rail_weight = self.get_weight_lbs(mr_profile, mid_rail_total_ft)

                items.append(self.make_material_item(
                    description=f"Fence mid-rails — {side_name} × {fence_mid_rail_count} ({mr_label}, {length_ft:.1f} ft each)",
                    material_type="square_tubing",
                    profile=mr_profile,
                    length_inches=length_in,
                    quantity=fence_mid_rail_count,
                    unit_price=round(length_ft * mr_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_TUBE,
                ))
                weight += mid_rail_weight
                weld_inches += self.weld_inches_for_joints(
                    post_count * fence_mid_rail_count * 2, 2.0)
                assumptions.append(
                    f"Fence {side_name}: {fence_mid_rail_count} mid-rail(s) ({mr_label}) for {height_in:.0f}\" height.")

            # Fence infill (pickets/bars matching gate or simplified)
            use_solid = "solid" in str(fence_match).lower() or "Solid" in infill_type
            use_pickets = (
                "Pickets" in infill_type or "Flat bar" in infill_type
                or "Horizontal" in infill_type
                or "match" in str(fence_match).lower()
            )

            if use_solid or "Expanded" in infill_type:
                # Sheet or expanded metal infill
                infill_sqft = self.sq_ft_from_dimensions(length_in, height_in)
                profile_key = "expanded_metal_13ga" if "Expanded" in infill_type else "sheet_14ga"
                sheet_price = lookup.get_price_per_sqft(profile_key)
                infill_sheets = self.apply_waste(math.ceil(infill_sqft / 32.0), self.WASTE_SHEET)
                infill_weight = self.get_plate_weight_lbs(length_in, height_in, 0.075)

                items.append(self.make_material_item(
                    description=f"Fence infill — {side_name} ({profile_key})",
                    material_type="plate",
                    profile=profile_key,
                    length_inches=length_in,
                    quantity=infill_sheets,
                    unit_price=round(32.0 * sheet_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                weight += infill_weight
                weld_inches += self.perimeter_inches(length_in, height_in) * 0.5
            elif use_pickets:
                # Vertical picket/bar infill
                # Use gate picket profile if fence should match gate and profile was resolved
                if gate_picket_profile and "match" in str(fence_match).lower():
                    picket_profile = gate_picket_profile
                else:
                    picket_profile = _resolve_picket_profile(fields, infill_type)
                picket_price_ft = lookup.get_price_per_foot(picket_profile)
                picket_count = math.ceil(length_in / infill_spacing_in) + 1
                picket_length_in = height_in - 2
                waste_rate = self.WASTE_FLAT if "Flat" in infill_type else self.WASTE_TUBE
                qty_with_waste = self.apply_waste(picket_count, waste_rate)
                picket_total_ft = self.inches_to_feet(picket_length_in * qty_with_waste)
                picket_weight = self.get_weight_lbs(picket_profile, picket_total_ft)

                items.append(self.make_material_item(
                    description="Fence pickets — %s × %d pcs (%d + %d%% waste)"
                                % (side_name, qty_with_waste, picket_count,
                                   int(waste_rate * 100)),
                    material_type="flat_bar" if "Flat" in infill_type else "square_tubing",
                    profile=picket_profile,
                    length_inches=picket_length_in,
                    quantity=qty_with_waste,
                    unit_price=round(self.inches_to_feet(picket_length_in) * picket_price_ft, 2),
                    cut_type="square",
                    waste_factor=waste_rate,
                ))
                weight += picket_weight
                weld_inches += self.weld_inches_for_joints(picket_count * 2, 1.5)

            # Fence square footage for finishing
            fence_sqft = self.sq_ft_from_dimensions(length_in, height_in) * 2  # Both sides
            sq_ft += fence_sqft

            assumptions.append(f"Adjacent fence {side_name}: {length_ft:.0f} ft, {post_count} posts.")

        return {
            "items": items,
            "hardware": hardware,
            "weight": weight,
            "sq_ft": sq_ft,
            "weld_inches": weld_inches,
            "assumptions": assumptions,
        }

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
