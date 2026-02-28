"""
PDF Quote Generator — Stage 6.

Generates professional PDF quote documents from PricedQuote data.
Uses fpdf2 (pure Python, no system dependencies).

All 8 sections always present:
1. Header + Job Summary
2. Material Breakdown
3. Cut List
4. Hardware & Parts
5. Labor Breakdown
6. Finishing
7. Project Total
8. Assumptions & Exclusions

White-labeled: uses shop name/logo from user profile, no CreateStage branding.
"""

from datetime import datetime
from io import BytesIO

from fpdf import FPDF


# --- Job type display names ---
JOB_TYPE_NAMES = {
    "cantilever_gate": "Cantilever Sliding Gate",
    "swing_gate": "Swing Gate",
    "straight_railing": "Straight Railing",
    "stair_railing": "Stair Railing",
    "repair_decorative": "Decorative Iron Repair",
    "ornamental_fence": "Ornamental Fence",
    "complete_stair": "Complete Staircase",
    "spiral_stair": "Spiral Staircase",
    "window_security_grate": "Window Security Grate",
    "balcony_railing": "Balcony Railing",
    "furniture_table": "Steel Furniture / Table",
    "utility_enclosure": "Utility Enclosure",
    "bollard": "Bollard",
    "repair_structural": "Structural Repair",
    "custom_fab": "Custom Fabrication",
}

# Labor process display names
PROCESS_NAMES = {
    "layout_setup": "Layout & Setup",
    "cut_prep": "Cut & Prep",
    "fit_tack": "Fit & Tack",
    "full_weld": "Full Weld",
    "grind_clean": "Grind & Clean",
    "finish_prep": "Finish Prep",
    "clearcoat": "Clear Coat",
    "paint": "Paint",
    "hardware_install": "Hardware Install",
    "site_install": "Site Install",
    "final_inspection": "Final Inspection",
}


def generate_job_summary(job_type: str, fields: dict) -> str:
    """
    Generate a plain-language description of the job from structured fields.
    Template-based per job type. Used in PDF header and quote history.
    """
    jt_name = JOB_TYPE_NAMES.get(job_type, job_type.replace("_", " ").title())
    parts = []

    if job_type in ("cantilever_gate", "swing_gate"):
        width = fields.get("clear_width", "")
        height = fields.get("height", "")
        frame = fields.get("frame_material", "")
        infill = fields.get("infill_type", "")
        motor = fields.get("motor_brand", "")
        finish = fields.get("finish", "")
        install = fields.get("installation", "")
        has_motor = fields.get("has_motor", "")

        if width:
            parts.append(f"{width}' wide")
        parts.append(jt_name.lower())
        if height:
            parts.append(f"{height}' tall")
        if frame:
            parts.append(f"with {_short(frame)} frame")
        if infill:
            parts.append(f"and {_short(infill)} infill")
        summary = ", ".join(parts[:2]) + (", " + ", ".join(parts[2:]) if len(parts) > 2 else "")

        extras = []
        if "yes" in str(has_motor).lower() and motor:
            extras.append(f"Includes {_short(motor)} electric operator")
        elif "yes" in str(has_motor).lower():
            extras.append("Includes electric operator")
        if finish:
            extras.append(f"{_short(finish)} finish")
        if install and "install" in str(install).lower():
            extras.append("Full site installation included")
        if extras:
            summary += ". " + ". ".join(extras)
        return summary + "."

    elif job_type in ("straight_railing", "stair_railing", "balcony_railing"):
        footage = fields.get("linear_footage", "")
        height = fields.get("railing_height", "")
        infill = fields.get("infill_style", "")
        finish = fields.get("finish", "")
        install = fields.get("installation", "")

        if footage:
            parts.append(f"{footage}' linear")
        parts.append(jt_name.lower())
        if height:
            parts.append(f"{_short(height)} tall")
        if infill:
            parts.append(f"with {_short(infill)} infill")
        if finish:
            parts.append(f"{_short(finish)} finish")
        if install and "install" in str(install).lower():
            parts.append("Full installation included")
        return ". ".join([", ".join(parts[:3])] + parts[3:]) + "."

    elif "repair" in job_type:
        repair_type = fields.get("repair_type", "")
        damage = fields.get("damage_description", "")
        parts.append(jt_name)
        if repair_type:
            parts.append(f"({_short(repair_type)})")
        if damage:
            parts.append(f"— {damage[:80]}")
        return " ".join(parts) + "."

    else:
        # Generic summary
        parts.append(jt_name)
        for key in ("width", "height", "length", "size", "linear_footage", "clear_width"):
            val = fields.get(key, "")
            if val:
                parts.append(f"{key.replace('_', ' ')}: {val}")
        finish = fields.get("finish", "")
        if finish:
            parts.append(f"{_short(finish)} finish")
        return ". ".join(parts) + "."


def _short(val: str) -> str:
    """Shorten option text to first meaningful part."""
    if not val:
        return ""
    # Take text before " (" or " —"
    for sep in [" (", " —", " -"]:
        if sep in val:
            val = val[:val.index(sep)]
    return val.strip()


def _fmt(amount) -> str:
    """Format a number as $X,XXX.XX"""
    try:
        return f"${float(amount):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"


def _fmt_hrs(hours) -> str:
    """Format hours as X.X"""
    try:
        return f"{float(hours):.1f}"
    except (ValueError, TypeError):
        return "0.0"


def _safe(text: str) -> str:
    """Replace Unicode chars that can't be rendered by built-in PDF fonts (latin-1)."""
    if not text:
        return ""
    return (
        text
        .replace("\u2022", "-")    # bullet
        .replace("\u2014", " - ")  # em dash
        .replace("\u2013", "-")    # en dash
        .replace("\u201c", '"')    # left double quote
        .replace("\u201d", '"')    # right double quote
        .replace("\u2018", "'")    # left single quote
        .replace("\u2019", "'")    # right single quote
        .encode("latin-1", errors="replace")
        .decode("latin-1")
    )


class QuotePDF(FPDF):
    """Custom PDF class for professional quote documents."""

    def __init__(self, shop_name="", shop_info=""):
        super().__init__()
        self.shop_name = shop_name
        self.shop_info = shop_info
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        pass  # We handle headers manually per section

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def section_header(self, title):
        """Render a section header bar."""
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(45, 55, 72)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def table_header(self, cols):
        """Render a table header row. cols: [(label, width), ...]"""
        self.set_font("Helvetica", "B", 8)
        self.set_fill_color(240, 240, 240)
        for label, width in cols:
            align = "R" if label in ("Qty", "Unit", "Total", "Hours", "Rate") else "L"
            self.cell(width, 6, label, border="B", fill=True, align=align)
        self.ln()

    def table_row(self, values, widths, bold=False):
        """Render a table data row."""
        self.set_font("Helvetica", "B" if bold else "", 8)
        for i, (val, width) in enumerate(zip(values, widths)):
            align = "R" if i >= len(widths) - 2 else "L"
            if bold:
                align = "R" if i == len(widths) - 1 else "L"
            self.cell(width, 5.5, str(val), align=align)
        self.ln()

    def subtotal_row(self, label, amount):
        """Render a subtotal row spanning the full width."""
        self.set_font("Helvetica", "B", 9)
        self.cell(140, 6, label, align="R", border="T")
        self.cell(50, 6, _fmt(amount), align="R", border="T")
        self.ln(8)


def generate_quote_pdf(
    priced_quote: dict,
    user_profile: dict,
    inputs: dict = None,
) -> bytes:
    """
    Generate a PDF quote document.

    Args:
        priced_quote: PricedQuote dict (from outputs_json)
        user_profile: User profile dict (shop_name, etc.)
        inputs: QuoteParams dict (from inputs_json) — for job summary

    Returns:
        PDF bytes
    """
    shop_name = user_profile.get("shop_name") or "Quote"
    shop_address = user_profile.get("shop_address") or ""
    shop_phone = user_profile.get("shop_phone") or ""
    shop_email = user_profile.get("shop_email") or ""

    shop_info_parts = [p for p in [shop_address, shop_phone, shop_email] if p]
    shop_info = " | ".join(shop_info_parts)

    pdf = QuotePDF(shop_name=shop_name, shop_info=shop_info)
    pdf.alias_nb_pages()
    pdf.add_page()
    pw = pdf.w - pdf.l_margin - pdf.r_margin  # printable width

    # ── SECTION 1: Header ──
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, shop_name, new_x="LMARGIN", new_y="NEXT")

    if shop_info:
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, shop_info, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(4)

    # Quote number and date
    quote_number = priced_quote.get("quote_number") or f"Q-{priced_quote.get('quote_id', '?')}"
    created = priced_quote.get("created_at", "")
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        date_str = dt.strftime("%B %d, %Y")
    except (ValueError, AttributeError):
        date_str = datetime.utcnow().strftime("%B %d, %Y")

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, f"QUOTE #{quote_number}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"Date: {date_str}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, "Valid for: 30 days", new_x="LMARGIN", new_y="NEXT")

    # Client name
    client = priced_quote.get("client_name")
    if client:
        pdf.ln(2)
        pdf.cell(0, 5, f"Prepared for: {client}", new_x="LMARGIN", new_y="NEXT")

    # Job summary
    pdf.ln(4)
    job_type = priced_quote.get("job_type", "")
    jt_display = JOB_TYPE_NAMES.get(job_type, job_type.replace("_", " ").title())
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, f"Job: {jt_display}", new_x="LMARGIN", new_y="NEXT")

    fields = (inputs or {}).get("fields", {})
    summary = generate_job_summary(job_type, fields)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 4.5, _safe(summary))
    pdf.ln(6)

    # ── SECTION 2: Materials ──
    materials = priced_quote.get("materials", [])
    pdf.section_header("MATERIALS")
    cols = [("Material", 70), ("Spec", 40), ("Qty", 20), ("Unit", 30), ("Total", 30)]
    widths = [c[1] for c in cols]
    pdf.table_header(cols)

    for item in materials:
        desc = item.get("description", "")
        profile = item.get("profile", "")
        qty_val = item.get("quantity", 1)
        unit_price = item.get("unit_price", 0)
        total = item.get("line_total", 0)
        # Split description for cleaner display
        short_desc = desc[:35] if len(desc) > 35 else desc
        pdf.table_row(
            [_safe(short_desc), _safe(profile[:20]), str(qty_val), _fmt(unit_price), _fmt(total)],
            widths,
        )

    material_sub = priced_quote.get("material_subtotal", 0)
    pdf.subtotal_row("Material Subtotal", material_sub)

    # ── SECTION 3: Cut List ──
    pdf.section_header("CUT LIST")
    cut_cols = [("Piece", 60), ("Material", 40), ("Length", 30), ("Qty", 20), ("Cut Type", 40)]
    cut_widths = [c[1] for c in cut_cols]
    pdf.table_header(cut_cols)

    for item in materials:
        desc = item.get("description", "")[:30]
        profile = item.get("profile", "")[:20]
        length = item.get("length_inches")
        qty = item.get("quantity", 1)
        cut = item.get("cut_type", "square")
        length_str = f'{length}"' if length else "-"
        pdf.table_row([_safe(desc), _safe(profile), length_str, str(qty), _safe(cut)], cut_widths)

    pdf.ln(4)

    # ── SECTION 4: Hardware & Parts ──
    hardware = priced_quote.get("hardware", [])
    consumables = priced_quote.get("consumables", [])
    pdf.section_header("HARDWARE & PARTS")
    hw_cols = [("Item", 70), ("Supplier", 40), ("Qty", 15), ("Unit", 30), ("Total", 35)]
    hw_widths = [c[1] for c in hw_cols]
    pdf.table_header(hw_cols)

    for item in hardware:
        desc = _safe(item.get("description", "")[:35])
        qty = item.get("quantity", 1)
        options = item.get("options", [])
        # Find cheapest option for display
        if options:
            valid = [o for o in options if o.get("price") is not None]
            if valid:
                cheapest = min(valid, key=lambda o: o["price"])
                supplier = _safe(cheapest.get("supplier", "")[:20])
                price = cheapest["price"]
                total = price * qty
                pdf.table_row([desc, supplier, str(qty), _fmt(price), _fmt(total)], hw_widths)
                # Show alternatives
                alts = [o for o in valid if o != cheapest]
                if alts:
                    alt_str = ", ".join(f"{_safe(o.get('supplier', ''))} {_fmt(o['price'])}" for o in alts[:2])
                    pdf.set_font("Helvetica", "I", 7)
                    pdf.set_text_color(120, 120, 120)
                    pdf.cell(70, 4, f"  Alt: {alt_str}", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_text_color(0, 0, 0)
            else:
                pdf.table_row([desc, "TBD", str(qty), "-", "-"], hw_widths)
        else:
            pdf.table_row([desc, "-", str(qty), "-", "-"], hw_widths)

    hw_sub = priced_quote.get("hardware_subtotal", 0)
    pdf.subtotal_row("Hardware Subtotal", hw_sub)

    # Consumables
    if consumables:
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Consumables", new_x="LMARGIN", new_y="NEXT")
        for c in consumables:
            pdf.set_font("Helvetica", "", 8)
            desc = _safe(c.get("description", "")[:50])
            total = c.get("line_total", 0)
            pdf.cell(140, 5, f"  {desc}", align="L")
            pdf.cell(50, 5, _fmt(total), align="R")
            pdf.ln()
        cons_sub = priced_quote.get("consumable_subtotal", 0)
        pdf.subtotal_row("Consumable Subtotal", cons_sub)

    # ── SECTION 5: Labor ──
    labor = priced_quote.get("labor", [])
    pdf.section_header("LABOR")
    labor_cols = [("Process", 70), ("Hours", 25), ("Rate", 35), ("Total", 60)]
    labor_widths = [c[1] for c in labor_cols]
    pdf.table_header(labor_cols)

    for proc in labor:
        name = PROCESS_NAMES.get(proc.get("process", ""), proc.get("process", ""))
        hours = proc.get("hours", 0)
        rate = proc.get("rate", 0)
        total = round(hours * rate, 2)
        if hours > 0:
            pdf.table_row([_safe(name), _fmt_hrs(hours), f"{_fmt(rate)}/hr", _fmt(total)], labor_widths)

    labor_sub = priced_quote.get("labor_subtotal", 0)
    pdf.subtotal_row("Labor Subtotal", labor_sub)

    # ── SECTION 6: Finishing ──
    finishing = priced_quote.get("finishing", {})
    pdf.section_header("FINISHING")
    method = finishing.get("method", "raw")
    area = finishing.get("area_sq_ft", 0)
    fin_total = finishing.get("total", 0)

    pdf.set_font("Helvetica", "", 9)
    method_display = method.replace("_", " ").title()
    outsource_cost = finishing.get("outsource_cost", 0)
    materials_cost = finishing.get("materials_cost", 0)

    if method == "raw":
        pdf.cell(0, 5, "Method: Raw Steel", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, "No finish applied - raw steel delivered as-is", new_x="LMARGIN", new_y="NEXT")
    elif outsource_cost > 0:
        pdf.cell(0, 5, f"Method: {method_display} (outsourced)", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, f"Area: {area:.0f} sq ft", new_x="LMARGIN", new_y="NEXT")
        rate = outsource_cost / area if area > 0 else 0
        pdf.cell(0, 5, f"Cost: {area:.0f} sq ft x {_fmt(rate)}/sqft = {_fmt(outsource_cost)}", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 5, f"Method: {method_display} (in-house)", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 5, f"Area: {area:.0f} sq ft", new_x="LMARGIN", new_y="NEXT")
        if materials_cost > 0:
            pdf.cell(0, 5, f"Materials: {_fmt(materials_cost)}", new_x="LMARGIN", new_y="NEXT")

    fin_sub = priced_quote.get("finishing_subtotal", fin_total)
    pdf.subtotal_row("Finishing Subtotal", fin_sub)

    # ── SECTION 7: Project Total ──
    pdf.section_header("PROJECT TOTAL")
    pdf.set_font("Helvetica", "", 10)

    totals = [
        ("Materials", priced_quote.get("material_subtotal", 0)),
        ("Hardware & Parts", priced_quote.get("hardware_subtotal", 0)),
        ("Consumables", priced_quote.get("consumable_subtotal", 0)),
        ("Labor", priced_quote.get("labor_subtotal", 0)),
        ("Finishing", priced_quote.get("finishing_subtotal", 0)),
    ]
    for label, amount in totals:
        pdf.cell(130, 6, label)
        pdf.cell(60, 6, _fmt(amount), align="R")
        pdf.ln()

    # Subtotal line
    subtotal = priced_quote.get("subtotal", 0)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(1)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(130, 7, "Subtotal")
    pdf.cell(60, 7, _fmt(subtotal), align="R")
    pdf.ln()

    # Markup
    markup_pct = priced_quote.get("selected_markup_pct", 0)
    if markup_pct > 0:
        markup_amount = round(subtotal * markup_pct / 100.0, 2)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(130, 6, f"Markup ({markup_pct}%)")
        pdf.cell(60, 6, _fmt(markup_amount), align="R")
        pdf.ln()

    # Grand total
    total = priced_quote.get("total", 0)
    pdf.ln(1)
    pdf.set_fill_color(45, 55, 72)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(130, 10, "  QUOTE TOTAL", fill=True)
    pdf.cell(60, 10, f"{_fmt(total)}  ", fill=True, align="R")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(14)

    # ── SECTION 8: Assumptions & Exclusions ──
    assumptions = priced_quote.get("assumptions", [])
    exclusions = priced_quote.get("exclusions", [])

    if assumptions:
        pdf.section_header("ASSUMPTIONS")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_x(pdf.l_margin)
        for a in assumptions:
            pdf.set_x(pdf.l_margin)
            pdf.cell(pw, 4.5, _safe(f"  - {a}"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)

    if exclusions:
        pdf.section_header("EXCLUSIONS")
        pdf.set_font("Helvetica", "", 8)
        pdf.set_x(pdf.l_margin)
        for e in exclusions:
            pdf.set_x(pdf.l_margin)
            pdf.cell(pw, 4.5, _safe(f"  - {e}"), new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # Terms
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.set_x(pdf.l_margin)
    pdf.cell(pw, 4, "This quote is valid for 30 days from the date above.", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(pw, 4, "Payment terms: 50% deposit, balance upon completion.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    return pdf.output()
