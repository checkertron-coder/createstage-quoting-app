"""
Balcony railing calculator.

Delegates railing portion to StraightRailingCalculator.
Adds structural frame if balcony_structure=true.
"""

from .base import BaseCalculator
from .straight_railing import StraightRailingCalculator
from .material_lookup import MaterialLookup

lookup = MaterialLookup()


class BalconyRailingCalculator(BaseCalculator):

    def calculate(self, fields: dict) -> dict:
        items = []
        hardware = []
        total_weight = 0.0
        total_sq_ft = 0.0
        total_weld_inches = 0.0
        assumptions = [
            "Material prices based on market averages — update with supplier quotes for accuracy.",
        ]

        # Delegate railing to StraightRailingCalculator
        railing_calc = StraightRailingCalculator()
        railing_result = railing_calc.calculate(fields)

        items.extend(railing_result["items"])
        hardware.extend(railing_result["hardware"])
        total_weight += railing_result["total_weight_lbs"]
        total_sq_ft += railing_result["total_sq_ft"]
        total_weld_inches += railing_result["weld_linear_inches"]
        assumptions.extend(railing_result.get("assumptions", [])[1:])  # Skip duplicate price note

        # Check if structural balcony frame is needed
        has_structure = "yes" in str(fields.get("balcony_structure",
                                                 fields.get("structural_frame", "No"))).lower()

        if has_structure:
            linear_footage = self.parse_feet(fields.get("linear_footage"), default=10.0)
            depth_ft = self.parse_feet(fields.get("balcony_depth",
                                                   fields.get("projection")), default=4.0)
            linear_in = self.feet_to_inches(linear_footage)
            depth_in = self.feet_to_inches(depth_ft)

            # Structural frame — HSS tube
            frame_profile = "sq_tube_2x2_11ga"
            frame_price_ft = lookup.get_price_per_foot(frame_profile)

            # Perimeter frame + cross members
            frame_perim_in = 2 * (linear_in + depth_in)
            cross_count = max(int(linear_footage / 4), 1)  # Every 4 ft
            cross_in = depth_in * cross_count
            total_frame_in = frame_perim_in + cross_in
            total_frame_ft = self.inches_to_feet(total_frame_in)
            frame_weight = self.get_weight_lbs(frame_profile, total_frame_ft)

            items.append(self.make_material_item(
                description="Balcony structural frame — 2\" sq tube 11ga (%.1f ft perimeter + %d cross members)" % (
                    self.inches_to_feet(frame_perim_in), cross_count),
                material_type="square_tubing",
                profile=frame_profile,
                length_inches=total_frame_in,
                quantity=self.linear_feet_to_pieces(total_frame_ft),
                unit_price=round(total_frame_ft * frame_price_ft / max(
                    self.linear_feet_to_pieces(total_frame_ft), 1), 2),
                cut_type="miter_45",
                waste_factor=self.WASTE_TUBE,
            ))
            total_weight += frame_weight
            total_weld_inches += self.weld_inches_for_joints((cross_count + 4) * 2, 3.0)

            # Deck plate
            deck_sqft = self.sq_ft_from_dimensions(linear_in, depth_in)
            total_sq_ft += deck_sqft

            assumptions.append(
                "Structural balcony frame: %.0f ft × %.0f ft with %d cross members." % (
                    linear_footage, depth_ft, cross_count))
        else:
            assumptions.append("Railing only — no structural balcony frame. Existing structure assumed adequate.")

        return self.make_material_list(
            job_type="balcony_railing",
            items=items,
            hardware=hardware,
            total_weight_lbs=total_weight,
            total_sq_ft=total_sq_ft,
            weld_linear_inches=total_weld_inches,
            assumptions=assumptions,
        )
