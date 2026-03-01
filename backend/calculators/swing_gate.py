"""
Swing gate material calculator.

Key differences from cantilever:
- No counterbalance tail
- Single vs double panel logic
- Hinge count/type must match gate weight
- Swing clearance and auto-close mechanisms
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class SwingGateCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        gate_panel_weight = 0.0  # Track for hinge sizing
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Try AI cut list for custom/complex designs
        if self._has_description(fields):
            ai_cuts = self._try_ai_cut_list("swing_gate", fields)
            if ai_cuts is not None:
                return self._build_from_ai_cuts("swing_gate", ai_cuts, fields, assumptions)

        # --- Parse inputs ---
        clear_width_ft = self.parse_feet(fields.get("clear_width"), default=8.0)
        height_ft = self.parse_feet(fields.get("height"), default=6.0)
        clear_width_in = self.feet_to_inches(clear_width_ft)
        height_in = self.feet_to_inches(height_ft)

        panel_config = fields.get("panel_config", "Single panel (one leaf)")
        is_double = "Double" in panel_config
        is_unequal = "unequal" in panel_config.lower() if is_double else False

        frame_size = fields.get("frame_size", "2\" x 2\"")
        frame_gauge_raw = fields.get("frame_gauge", "11 gauge (0.120\" - standard)")
        frame_gauge = self._normalize_gauge(frame_gauge_raw)

        infill_type = fields.get("infill_type", "Pickets (vertical bars)")
        infill_spacing_in = self._parse_spacing(fields.get("picket_spacing",
                                                           fields.get("flat_bar_spacing", "4\" on-center")))

        post_size = fields.get("post_size", "4\" x 4\" square tube")
        post_count_raw = fields.get("post_count", "")
        hinge_type = fields.get("hinge_type", "Heavy duty weld-on barrel hinges")
        hinge_count_raw = fields.get("hinge_count", "")
        latch_type = fields.get("latch_type", "Gravity latch")
        auto_close = fields.get("auto_close", "No")
        center_stop = fields.get("center_stop", "")

        has_motor = "Yes" in fields.get("has_motor", "No")
        motor_brand = fields.get("motor_brand", "")

        finish = fields.get("finish", "Powder coat")

        # --- Panel geometry ---
        if is_double:
            if is_unequal:
                # Typical: 2/3 active, 1/3 fixed
                panel_widths_in = [clear_width_in * 2.0 / 3.0, clear_width_in / 3.0]
                assumptions.append("Unequal double: 2/3 active panel + 1/3 fixed panel.")
            else:
                panel_widths_in = [clear_width_in / 2.0, clear_width_in / 2.0]
            num_panels = 2
        else:
            panel_widths_in = [clear_width_in]
            num_panels = 1

        # Frame profile lookup
        frame_key = self._lookup_frame(frame_size, frame_gauge)
        frame_price_ft = lookup.get_price_per_foot(frame_key)

        # --- 1. Gate panels (frame + mid-rails) ---
        for i, panel_width_in in enumerate(panel_widths_in):
            panel_label = f"Panel {i+1}" if num_panels > 1 else "Gate panel"

            # Frame perimeter
            frame_perim_in = self.perimeter_inches(panel_width_in, height_in)

            # Cross members: 1 mid-rail for gates over 48", 2 for over 72"
            mid_rail_count = 0
            if height_in > 48:
                mid_rail_count = 1
            if height_in > 72:
                mid_rail_count = 2
            mid_rail_total_in = panel_width_in * mid_rail_count

            total_frame_in = frame_perim_in + mid_rail_total_in
            total_frame_ft = self.inches_to_feet(total_frame_in)
            frame_weight = self.get_weight_lbs(frame_key, total_frame_ft)

            items.append(self.make_material_item(
                description=f"{panel_label} frame — {frame_size} {frame_gauge} ({total_frame_ft:.1f} ft incl. {mid_rail_count} mid-rail)",
                material_type="square_tubing",
                profile=frame_key,
                length_inches=total_frame_in,
                quantity=self.linear_feet_to_pieces(total_frame_ft),
                unit_price=round(total_frame_ft * frame_price_ft / max(self.linear_feet_to_pieces(total_frame_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight
            gate_panel_weight += frame_weight

            # Weld: 4 corners + mid-rail joints
            total_weld_inches += self.weld_inches_for_joints(4, height_in * 0.12)
            total_weld_inches += self.weld_inches_for_joints(mid_rail_count * 2, 3.0)

            # --- Infill ---
            face_width_in = panel_width_in
            face_height_in = height_in

            if "Pickets" in infill_type or "Flat bar" in infill_type:
                is_flat = "Flat" in infill_type
                picket_profile = "flat_bar_1x0.25" if is_flat else "sq_bar_0.75"
                picket_price_ft = lookup.get_price_per_foot(picket_profile)
                picket_count = math.ceil(face_width_in / infill_spacing_in) + 1
                picket_length_in = face_height_in - 4  # Minus top/bottom rail heights
                picket_total_ft = self.inches_to_feet(picket_length_in * picket_count)
                picket_weight = self.get_weight_lbs(picket_profile, picket_total_ft)
                waste = self.WASTE_FLAT if is_flat else self.WASTE_TUBE

                items.append(self.make_material_item(
                    description=f"{panel_label} infill — {infill_type} at {infill_spacing_in}\" OC × {picket_count} pcs",
                    material_type="flat_bar" if is_flat else "square_tubing",
                    profile=picket_profile,
                    length_inches=picket_length_in,
                    quantity=self.apply_waste(picket_count, waste),
                    unit_price=round(self.inches_to_feet(picket_length_in) * picket_price_ft, 2),
                    cut_type="square",
                    waste_factor=waste,
                ))
                total_weight += picket_weight
                gate_panel_weight += picket_weight
                total_weld_inches += self.weld_inches_for_joints(picket_count * 2, 1.5)

            elif "Expanded" in infill_type:
                infill_sqft = self.sq_ft_from_dimensions(face_width_in, face_height_in)
                infill_sheets = self.apply_waste(math.ceil(infill_sqft / 32.0), self.WASTE_SHEET)
                sheet_price = lookup.get_price_per_sqft("expanded_metal_13ga")
                infill_weight = self.get_plate_weight_lbs(face_width_in, face_height_in, 0.075)

                items.append(self.make_material_item(
                    description=f"{panel_label} expanded metal infill — 13ga",
                    material_type="plate",
                    profile="expanded_metal_13ga",
                    length_inches=face_width_in,
                    quantity=infill_sheets,
                    unit_price=round(32.0 * sheet_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += infill_weight
                gate_panel_weight += infill_weight
                total_weld_inches += self.perimeter_inches(face_width_in, face_height_in) * 0.5

            elif "Solid" in infill_type:
                infill_sqft = self.sq_ft_from_dimensions(face_width_in, face_height_in)
                infill_sheets = self.apply_waste(math.ceil(infill_sqft / 32.0), self.WASTE_SHEET)
                sheet_price = lookup.get_price_per_sqft("sheet_14ga")
                infill_weight = self.get_plate_weight_lbs(face_width_in, face_height_in, 0.075)

                items.append(self.make_material_item(
                    description=f"{panel_label} solid sheet panel — 14ga",
                    material_type="plate",
                    profile="sheet_14ga",
                    length_inches=face_width_in,
                    quantity=infill_sheets,
                    unit_price=round(32.0 * sheet_price, 2),
                    cut_type="square",
                    waste_factor=self.WASTE_SHEET,
                ))
                total_weight += infill_weight
                gate_panel_weight += infill_weight

        # --- 2. Posts ---
        if "already exist" in str(post_count_raw).lower() or "already" in str(post_count_raw).lower():
            post_count = 0
            assumptions.append("Posts already in place — not included in material list.")
        elif is_double:
            post_count = 2  # Two hinge posts; center post optional
            if "3" in str(post_count_raw):
                post_count = 3
        else:
            post_count = 2  # Hinge side + latch side

        if post_count > 0:
            post_key = self._lookup_post(post_size)
            post_price_ft = lookup.get_price_per_foot(post_key)
            post_embed_in = 42.0  # Chicago frost line
            post_total_in = height_in + 2 + post_embed_in
            post_total_ft = self.inches_to_feet(post_total_in) * post_count
            post_weight = self.get_weight_lbs(post_key, post_total_ft)

            items.append(self.make_material_item(
                description=f"Posts — {post_size} × {post_count} ({self.inches_to_feet(post_total_in):.1f} ft each, {post_embed_in}\" embed)",
                material_type="square_tubing",
                profile=post_key,
                length_inches=post_total_in,
                quantity=post_count,
                unit_price=round(self.inches_to_feet(post_total_in) * post_price_ft, 2),
                cut_type="square",
                waste_factor=0.0,
            ))
            total_weight += post_weight

            # Post concrete
            hole_diameter_in = 12.0
            cu_in_per_hole = math.pi * (hole_diameter_in / 2) ** 2 * post_embed_in
            total_cu_yd = (cu_in_per_hole * post_count) / 46656.0
            concrete_price = lookup.get_unit_price("concrete_per_cuyd")

            items.append(self.make_material_item(
                description=f"Post concrete — {post_count} holes × 12\" dia × {post_embed_in}\" deep ({total_cu_yd:.2f} cu yd)",
                material_type="concrete",
                profile="concrete_footing",
                length_inches=post_embed_in,
                quantity=post_count,
                unit_price=round(total_cu_yd * concrete_price / post_count, 2),
                cut_type="n/a",
                waste_factor=0.0,
            ))

        # --- 3. Hinges ---
        # Weight-based hinge sizing
        per_panel_weight = gate_panel_weight / num_panels
        hinge_count = self._calc_hinge_count(per_panel_weight, hinge_count_raw)
        hinge_key = self._lookup_hinge(hinge_type, per_panel_weight)

        # Hinge count is per panel
        total_hinge_pairs = hinge_count * num_panels
        hardware.append(self.make_hardware_item(
            description=f"Gate hinge — {hinge_type} ({hinge_count} per panel × {num_panels} panel{'s' if num_panels > 1 else ''})",
            quantity=total_hinge_pairs,
            options=lookup.get_hardware_options(hinge_key),
        ))

        if per_panel_weight > 500:
            assumptions.append(f"WARNING: Panel weight estimated at {per_panel_weight:.0f} lbs — exceeds standard hinge capacity. Engineering review recommended.")

        # --- 4. Latch ---
        latch_key = self._lookup_latch(latch_type)
        if latch_key:
            hardware.append(self.make_hardware_item(
                description=f"Gate latch — {latch_type}",
                quantity=1,
                options=lookup.get_hardware_options(latch_key),
            ))

        # --- 5. Center stop / drop rod (double gates) ---
        if is_double and center_stop:
            stop_key = self._lookup_center_stop(center_stop)
            if stop_key:
                hardware.append(self.make_hardware_item(
                    description=f"Center stop — {center_stop}",
                    quantity=1,
                    options=lookup.get_hardware_options(stop_key),
                ))

        # --- 6. Auto-close mechanism ---
        if "spring" in str(auto_close).lower():
            hardware.append(self.make_hardware_item(
                description="Self-closing spring hinge pair",
                quantity=num_panels,
                options=lookup.get_hardware_options("spring_hinge_pair"),
            ))
        elif "hydraulic" in str(auto_close).lower():
            hardware.append(self.make_hardware_item(
                description="Hydraulic gate closer",
                quantity=num_panels,
                options=lookup.get_hardware_options("hydraulic_closer"),
            ))

        # --- 7. Motor ---
        if has_motor:
            motor_key = self._lookup_motor(motor_brand)
            hardware.append(self.make_hardware_item(
                description=f"Swing gate operator — {motor_brand or 'LiftMaster RSW12U'}",
                quantity=num_panels,  # Need one per panel for double
                options=lookup.get_hardware_options(motor_key),
            ))

        # --- 8. Gate stops ---
        hardware.append(self.make_hardware_item(
            description="Gate stop/bumper",
            quantity=2,
            options=lookup.get_hardware_options("gate_stop"),
        ))

        # --- Surface area for finishing ---
        total_sq_ft = sum(
            self.sq_ft_from_dimensions(w, height_in) * 2  # Both sides
            for w in panel_widths_in
        )

        return self.make_material_list(
            job_type="swing_gate",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    # --- Private helpers ---

    def _normalize_gauge(self, gauge_str: str) -> str:
        if "11" in gauge_str:
            return "11 gauge"
        elif "14" in gauge_str:
            return "14 gauge"
        elif "16" in gauge_str:
            return "16 gauge"
        return "11 gauge"

    def _lookup_frame(self, frame_size: str, frame_gauge: str) -> str:
        from .cantilever_gate import FRAME_PROFILES
        key = (frame_size, frame_gauge)
        if key in FRAME_PROFILES:
            return FRAME_PROFILES[key][0]
        return "sq_tube_2x2_11ga"

    def _lookup_post(self, post_size: str) -> str:
        from .cantilever_gate import POST_PROFILES
        if post_size in POST_PROFILES:
            return POST_PROFILES[post_size][0]
        return "sq_tube_4x4_11ga"

    def _parse_spacing(self, spacing_str: str) -> float:
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

    def _calc_hinge_count(self, panel_weight: float, user_input: str) -> int:
        """Determine hinge count based on gate weight, with user override."""
        # User specified
        if "2" in str(user_input):
            return 2
        if "3" in str(user_input):
            return 3
        if "4" in str(user_input):
            return 4
        # Weight-based
        if panel_weight < 150:
            return 2
        if panel_weight < 300:
            return 2
        if panel_weight < 500:
            return 3
        return 3  # Flag for review at > 500

    def _lookup_hinge(self, hinge_type: str, weight: float) -> str:
        """Select hinge from catalog based on type and weight."""
        h = str(hinge_type).lower()
        if "ball" in h or "bearing" in h:
            return "ball_bearing_hinge_pair"
        if weight > 150 or "heavy" in h:
            return "heavy_duty_weld_hinge_pair"
        return "standard_weld_hinge_pair"

    def _lookup_latch(self, latch_str: str) -> str:
        if not latch_str or "None" in latch_str:
            return ""
        latch = str(latch_str).lower()
        if "gravity" in latch:
            return "gravity_latch"
        if "magnetic" in latch:
            return "magnetic_latch"
        if "deadbolt" in latch or "keyed" in latch:
            return "keyed_deadbolt"
        if "pool" in latch:
            return "pool_code_latch"
        if "electric" in latch:
            return "electric_strike"
        return "gravity_latch"

    def _lookup_center_stop(self, stop_str: str) -> str:
        s = str(stop_str).lower()
        if "cane" in s:
            return "cane_bolt"
        if "surface" in s:
            return "surface_drop_rod"
        if "flush" in s:
            return "flush_bolt"
        return "cane_bolt"

    def _lookup_motor(self, brand: str) -> str:
        brand = str(brand).lower()
        if "rsw" in brand or ("liftmaster" in brand and "csw" not in brand):
            return "liftmaster_rsw12u"
        if "csw" in brand:
            return "liftmaster_csw24u"
        if "patriot" in brand or "us auto" in brand:
            return "us_automatic_patriot"
        return "liftmaster_rsw12u"
