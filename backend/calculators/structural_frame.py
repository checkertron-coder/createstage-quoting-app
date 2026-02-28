"""
Structural steel frame calculator.

Routes by frame_type (mezzanine, canopy, portal frame, equipment support).
Beams + columns + connections.
"""

import math

from .base import BaseCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class StructuralFrameCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Parse inputs
        frame_type = fields.get("frame_type", "Portal frame (beam + columns)")
        span_ft = self.parse_feet(fields.get("span"), default=20.0)
        height_ft = self.parse_feet(fields.get("height"), default=10.0)
        depth_ft = self.parse_feet(fields.get("depth"), default=0.0)
        span_in = self.feet_to_inches(span_ft)
        height_in = self.feet_to_inches(height_ft)

        material_str = fields.get("material", "Wide flange / I-beam (most common for structural)")

        # Select beam profile based on span
        beam_profile, beam_weight_per_ft = self._select_beam(span_ft, material_str)
        column_profile, col_weight_per_ft = self._select_column(height_ft, material_str)

        # Price per foot (structural steel priced ~$1/lb for mill, $1.50-2/lb delivered)
        beam_price_ft = beam_weight_per_ft * 1.50
        col_price_ft = col_weight_per_ft * 1.50

        if "mezzanine" in str(frame_type).lower():
            # Mezzanine: beams span, columns support, cross beams at depth intervals
            beam_count = 2  # Front and back beams
            column_count = 4  # Minimum 4 corners
            if depth_ft == 0:
                depth_ft = min(span_ft, 12.0)

            if span_ft > 20:
                column_count = 6  # Add intermediate columns
                beam_count = 3

            # Main beams
            beam_total_ft = span_ft * beam_count
            beam_weight = beam_weight_per_ft * beam_total_ft

            items.append(self.make_material_item(
                description="Main beams — %s × %d (%.0f ft span)" % (
                    beam_profile, beam_count, span_ft),
                material_type="mild_steel",
                profile=beam_profile,
                length_inches=span_in,
                quantity=beam_count,
                unit_price=round(span_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += beam_weight

            # Cross beams (depth direction)
            depth_in = self.feet_to_inches(depth_ft)
            cross_beam_count = beam_count + 1  # One more than main beams
            cross_total_ft = depth_ft * cross_beam_count
            cross_weight = beam_weight_per_ft * cross_total_ft * 0.6  # Lighter cross beams

            items.append(self.make_material_item(
                description="Cross beams — %s × %d (%.0f ft depth)" % (
                    beam_profile, cross_beam_count, depth_ft),
                material_type="mild_steel",
                profile=beam_profile,
                length_inches=depth_in,
                quantity=cross_beam_count,
                unit_price=round(depth_ft * beam_price_ft * 0.6, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += cross_weight

            total_sq_ft = span_ft * depth_ft  # Platform area
            assumptions.append("Mezzanine: %.0f ft × %.0f ft, %.0f ft clear height." % (
                span_ft, depth_ft, height_ft))

        elif "canopy" in str(frame_type).lower():
            # Canopy: beams across span, columns on one or both sides
            projection_ft = depth_ft if depth_ft > 0 else 10.0
            beam_count = max(int(span_ft / 10), 2)  # One rafter every ~10 ft
            column_count = beam_count

            # Rafters
            rafter_total_ft = projection_ft * beam_count
            rafter_weight = beam_weight_per_ft * rafter_total_ft

            items.append(self.make_material_item(
                description="Rafters — %s × %d (%.0f ft projection)" % (
                    beam_profile, beam_count, projection_ft),
                material_type="mild_steel",
                profile=beam_profile,
                length_inches=self.feet_to_inches(projection_ft),
                quantity=beam_count,
                unit_price=round(projection_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += rafter_weight

            # Header beam (connects rafters)
            header_weight = beam_weight_per_ft * span_ft

            items.append(self.make_material_item(
                description="Header beam — %s (%.0f ft span)" % (beam_profile, span_ft),
                material_type="mild_steel",
                profile=beam_profile,
                length_inches=span_in,
                quantity=1,
                unit_price=round(span_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += header_weight

            total_sq_ft = span_ft * projection_ft
            assumptions.append("Canopy: %.0f ft span × %.0f ft projection." % (span_ft, projection_ft))

        else:
            # Generic portal frame: beam + 2 columns (or more)
            column_count = 2
            beam_count = 1
            if span_ft > 30:
                column_count = 3
                beam_count = 2

            # Beam
            beam_weight = beam_weight_per_ft * span_ft * beam_count
            items.append(self.make_material_item(
                description="Beam — %s × %d (%.0f ft span)" % (beam_profile, beam_count, span_ft),
                material_type="mild_steel",
                profile=beam_profile,
                length_inches=span_in,
                quantity=beam_count,
                unit_price=round(span_ft * beam_price_ft, 2),
                cut_type="square",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += beam_weight
            total_sq_ft = span_ft * height_ft
            assumptions.append("Portal frame: %.0f ft span × %.0f ft height." % (span_ft, height_ft))

        # Columns (shared across all types)
        col_total_ft = height_ft * column_count
        col_weight = col_weight_per_ft * col_total_ft

        items.append(self.make_material_item(
            description="Columns — %s × %d (%.0f ft each)" % (
                column_profile, column_count, height_ft),
            material_type="mild_steel",
            profile=column_profile,
            length_inches=height_in,
            quantity=column_count,
            unit_price=round(height_ft * col_price_ft, 2),
            cut_type="square",
            waste_factor=self.WASTE_TUBE,
        ))
        total_weight += col_weight

        # Connection plates / gussets
        connection_count = column_count * 2  # Top and bottom of each column
        plate_weight = self.get_plate_weight_lbs(12, 12, 0.5) * connection_count

        items.append(self.make_material_item(
            description="Connection plates — 1/2\" × 12\" × 12\" × %d" % connection_count,
            material_type="plate",
            profile="plate_0.5",
            length_inches=12.0,
            quantity=connection_count,
            unit_price=round(plate_weight * 0.50 / max(connection_count, 1), 2),
            cut_type="square",
            waste_factor=self.WASTE_SHEET,
        ))
        total_weight += plate_weight

        # Weld totals
        total_weld_inches = connection_count * 48  # Perimeter weld each connection
        total_weld_inches += column_count * 24  # Base plate welds

        assumptions.append(
            "Structural steel priced at ~$1.50/lb delivered. "
            "Engineering/PE stamp not included — required for occupied structures.")

        return self.make_material_list(
            job_type="structural_frame",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )

    def _select_beam(self, span_ft, material_str):
        """Select beam profile and weight per foot based on span."""
        if "hss" in str(material_str).lower() or "tube" in str(material_str).lower():
            if span_ft <= 12:
                return ("sq_tube_4x4_11ga", 4.18)
            return ("rect_tube_2x4_11ga", 2.80)

        if "channel" in str(material_str).lower():
            if span_ft <= 15:
                return ("channel_6x8.2", 8.2)
            return ("channel_6x8.2", 8.2)

        # Default: wide flange (approximate as channel for pricing)
        if span_ft <= 15:
            return ("channel_6x8.2", 21.0)  # W8×21 equivalent
        if span_ft <= 25:
            return ("channel_6x8.2", 31.0)  # W8×31 equivalent
        return ("channel_6x8.2", 49.0)  # W10×49 equivalent

    def _select_column(self, height_ft, material_str):
        """Select column profile and weight per foot."""
        if "hss" in str(material_str).lower() or "tube" in str(material_str).lower():
            return ("sq_tube_4x4_11ga", 4.18)

        # Default: wide flange column
        if height_ft <= 12:
            return ("sq_tube_4x4_11ga", 21.0)  # W6×20 equivalent
        return ("sq_tube_4x4_11ga", 31.0)  # W8×31 equivalent
