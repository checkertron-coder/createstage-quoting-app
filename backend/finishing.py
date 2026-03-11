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
    ANODIZE_PER_SQFT = 5.00         # Type II anodizing (aluminum)
    CERAMIC_COAT_PER_SQFT = 6.00    # High-temp ceramic / bedliner
    PATINA_MATERIAL_PER_SQFT = 0.40  # Hot oil, chemical patina agents

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

        if method == "anodized":
            outsource_cost = round(area * self.ANODIZE_PER_SQFT, 2)
            prep_hours = self._extract_prep_hours(labor_processes)
            return {
                "method": "anodized",
                "area_sq_ft": round(area, 1),
                "hours": round(prep_hours, 2),
                "materials_cost": 0.0,
                "outsource_cost": outsource_cost,
                "total": round(outsource_cost, 2),
            }

        if method == "ceramic_coat":
            outsource_cost = round(area * self.CERAMIC_COAT_PER_SQFT, 2)
            return {
                "method": "ceramic_coat",
                "area_sq_ft": round(area, 1),
                "hours": 0.0,
                "materials_cost": 0.0,
                "outsource_cost": outsource_cost,
                "total": round(outsource_cost, 2),
            }

        if method == "patina":
            materials_cost = round(area * self.PATINA_MATERIAL_PER_SQFT, 2)
            return {
                "method": "patina",
                "area_sq_ft": round(area, 1),
                "hours": round(finish_hours, 2),
                "materials_cost": materials_cost,
                "outsource_cost": 0.0,
                "total": round(materials_cost, 2),
            }

        if method == "brushed":
            # Brushed/polished — labor-only, no material cost
            return {
                "method": "brushed",
                "area_sq_ft": round(area, 1),
                "hours": round(finish_hours, 2),
                "materials_cost": 0.0,
                "outsource_cost": 0.0,
                "total": 0.0,
            }

        # Fallback — treat unknown as paint (has material cost)
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
        """Normalize free-text finish answer to a standard type.

        Standard types: raw, clearcoat, paint, powder_coat, galvanized,
        anodized, ceramic_coat, patina, brushed.

        Every question tree option must map to one of these. If you add a
        new option to a question tree, add its keywords here.
        """
        f = str(finish_type).lower().strip()
        if not f:
            return "raw"

        # --- Brushed / polished / mirror (in-house labor) ---
        # MUST come before raw check: "Brushed stainless (no coating)" contains
        # "no coating" which would match the raw block if checked first.
        if any(k in f for k in ("brush", "polish", "mirror", "satin",
                                 "scotch-brite")):
            return "brushed"

        # --- Clear coat (in-house) ---
        # MUST come before raw: "clear" is unambiguous and never means raw.
        if any(k in f for k in ("clear", "urethane", "permalac", "lacquer", "wax")):
            return "clearcoat"

        # --- Powder coat (outsourced) ---
        if "powder" in f:
            return "powder_coat"

        # --- Galvanized (outsourced) ---
        if "galv" in f or "hot dip" in f or "hot-dip" in f:
            return "galvanized"

        # --- Anodized (outsourced, aluminum) ---
        if "anodiz" in f:
            return "anodized"

        # --- Ceramic coat / bedliner (outsourced) ---
        if any(k in f for k in ("ceramic", "bedliner", "bed liner", "line-x",
                                 "rhino", "cerakote")):
            return "ceramic_coat"

        # --- Patina / blackened / aged (in-house) ---
        if any(k in f for k in ("patina", "blacken", "aged", "corten",
                                 "hot oil", "rust finish")):
            return "patina"

        # --- Paint / primer / match existing / refinish (in-house) ---
        if any(k in f for k in ("paint", "primer", "prime only", "match existing",
                                 "refinish", "recoat", "fireproof", "intumescent")):
            return "paint"

        # --- Explicit raw / no-finish / by-others ---
        # Now safe as a late check: all specific finishes already matched above.
        # "Raw steel", "No finish", "Bare metal", "Thermal wrap (by others)",
        # "Bollard cover/sleeve (plastic — by others)", "Mill finish",
        # "Not sure — recommend based on use", "No coating"
        if any(k in f for k in ("raw", "no finish", "bare", "mill finish",
                                 "by others", "not sure", "no coating",
                                 "thermal wrap")):
            return "raw"

        # --- None of the above — "none" check last (avoid "none" matching "no" inside words) ---
        if f in ("none",):
            return "raw"

        # Unknown — fall through to the build() fallback which prices as paint
        # rather than silently discarding as "raw"
        return f

    def _extract_finish_hours(self, method: str, labor_processes: list) -> float:
        """Sum hours for finish-related processes."""
        finish_process_names = set()
        if method == "clearcoat":
            finish_process_names = {"finish_prep", "clearcoat",
                                    "coating_application"}
        elif method in ("paint", "patina"):
            finish_process_names = {"finish_prep", "paint",
                                    "coating_application"}
        elif method in ("powder_coat", "anodized", "ceramic_coat"):
            finish_process_names = {"finish_prep"}
        elif method == "brushed":
            finish_process_names = {"finish_prep", "grind_clean"}
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
