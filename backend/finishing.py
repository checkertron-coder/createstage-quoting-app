"""
Finishing Section Builder — builds the FinishingSection from CLAUDE.md contract.

FINISHING IS NEVER OPTIONAL — even raw steel gets a finishing section.
This is the most commonly underquoted item in fabrication.
Making it always visible is a core product principle.
"""


class FinishingBuilder:
    """
    Builds the FinishingSection for the quote output.

    Takes finish-related labor processes and material_list square footage
    and assembles the FinishingSection TypedDict from CLAUDE.md.
    """

    # Outsource costs per sq ft
    POWDER_COAT_PER_SQFT = 3.50     # Mid-range, varies $2.50-5.00
    GALVANIZE_PER_SQFT = 2.00       # Hot-dip galvanizing
    ZINC_SPRAY_PER_SQFT = 1.50      # Cold galvanizing spray

    # In-house material costs per sq ft
    CLEARCOAT_MATERIAL_PER_SQFT = 0.35
    PAINT_MATERIAL_PER_SQFT = 0.50  # Primer + topcoat

    def build(self, finish_type: str, total_sq_ft: float,
              labor_processes: list, is_outsourced: bool = False) -> dict:
        """
        Build a FinishingSection dict matching CLAUDE.md contract.

        Args:
            finish_type: "raw" | "clearcoat" | "paint" | "powder_coat" | "galvanized"
            total_sq_ft: from MaterialList.total_sq_ft
            labor_processes: list of LaborProcess dicts (to extract finish-related hours)
            is_outsourced: True for powder coat and galvanizing (typically outsourced)

        Returns:
            FinishingSection dict:
            {
                method: str,
                area_sq_ft: float,
                hours: float,
                materials_cost: float,
                outsource_cost: float,
                total: float,
            }
        """
        # Normalize finish type
        method = self._normalize_finish_type(finish_type)

        # Ensure area is always positive (even raw steel has a surface)
        area = max(total_sq_ft, 1.0)

        # Extract finish-related hours from labor processes
        finish_hours = self._extract_finish_hours(method, labor_processes)

        if method == "raw":
            return {
                "method": "raw",
                "area_sq_ft": round(area, 1),
                "hours": 0.0,
                "materials_cost": 0.0,
                "outsource_cost": 0.0,
                "total": 0.0,
            }

        if method == "clearcoat":
            materials_cost = round(area * self.CLEARCOAT_MATERIAL_PER_SQFT, 2)
            return {
                "method": "clearcoat",
                "area_sq_ft": round(area, 1),
                "hours": round(finish_hours, 2),
                "materials_cost": materials_cost,
                "outsource_cost": 0.0,
                "total": round(materials_cost, 2),
            }

        if method == "paint":
            materials_cost = round(area * self.PAINT_MATERIAL_PER_SQFT, 2)
            return {
                "method": "paint",
                "area_sq_ft": round(area, 1),
                "hours": round(finish_hours, 2),
                "materials_cost": materials_cost,
                "outsource_cost": 0.0,
                "total": round(materials_cost, 2),
            }

        if method == "powder_coat":
            outsource_cost = round(area * self.POWDER_COAT_PER_SQFT, 2)
            # Powder coat is outsourced — in-house hours are just prep
            prep_hours = self._extract_prep_hours(labor_processes)
            return {
                "method": "powder_coat",
                "area_sq_ft": round(area, 1),
                "hours": round(prep_hours, 2),
                "materials_cost": 0.0,
                "outsource_cost": outsource_cost,
                "total": round(outsource_cost, 2),
            }

        if method == "galvanized":
            outsource_cost = round(area * self.GALVANIZE_PER_SQFT, 2)
            return {
                "method": "galvanized",
                "area_sq_ft": round(area, 1),
                "hours": 0.0,
                "materials_cost": 0.0,
                "outsource_cost": outsource_cost,
                "total": round(outsource_cost, 2),
            }

        # Fallback — treat unknown as paint
        materials_cost = round(area * self.PAINT_MATERIAL_PER_SQFT, 2)
        return {
            "method": method,
            "area_sq_ft": round(area, 1),
            "hours": round(finish_hours, 2),
            "materials_cost": materials_cost,
            "outsource_cost": 0.0,
            "total": round(materials_cost, 2),
        }

    def _normalize_finish_type(self, finish_type: str) -> str:
        """Normalize free-text finish answer to one of the 5 standard types."""
        f = str(finish_type).lower()
        if "raw" in f or "none" in f or "no finish" in f:
            return "raw"
        if "clear" in f:
            return "clearcoat"
        if "powder" in f:
            return "powder_coat"
        if "galv" in f or "hot dip" in f or "hot-dip" in f:
            return "galvanized"
        if "paint" in f or "primer" in f:
            return "paint"
        # Default: if they said something but we can't parse, treat as paint
        if f and f != "raw":
            return "paint"
        return "raw"

    def _extract_finish_hours(self, method: str, labor_processes: list) -> float:
        """Sum hours for finish-related processes."""
        finish_process_names = set()
        if method == "clearcoat":
            finish_process_names = {"finish_prep", "clearcoat"}
        elif method == "paint":
            finish_process_names = {"finish_prep", "paint"}
        elif method == "powder_coat":
            finish_process_names = {"finish_prep"}
        # raw and galvanized have 0 in-house hours

        total = 0.0
        for p in labor_processes:
            if p.get("process") in finish_process_names:
                total += p.get("hours", 0.0)
        return total

    def _extract_prep_hours(self, labor_processes: list) -> float:
        """Extract just the finish_prep hours."""
        for p in labor_processes:
            if p.get("process") == "finish_prep":
                return p.get("hours", 0.0)
        return 0.0
