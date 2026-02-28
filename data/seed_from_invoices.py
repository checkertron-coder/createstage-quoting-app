#!/usr/bin/env python3
"""
Seed material prices and historical labor actuals from invoice JSON files.

Usage:
    python data/seed_from_invoices.py

Handles four file formats:
  - osorio_prices_seed.json  — Osorio Metals per-foot prices
  - wexler_prices_raw.json   — D. Wexler & Sons material estimates
  - createstage_invoices.json — Completed CreateStage job invoices
  - firetable_pro_bom.json   — FireTable Pro bill of materials

Outputs:
  - data/seeded_prices.json — Merged per-profile prices for MaterialLookup
  - historical_actuals DB rows — From invoice data (labor hours, costs)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# ---------------------------------------------------------------------------
# Material description → profile key parser
# ---------------------------------------------------------------------------

# Gauge to decimal inches
_GAUGE_MAP = {
    "7ga": 0.1875, "10ga": 0.1345, "11ga": 0.1196, "14ga": 0.0747,
    "16ga": 0.0598, "18ga": 0.0478, "20ga": 0.0359, "22ga": 0.0299,
}

# Fraction to decimal
_FRAC_MAP = {
    "1/8": 0.125, "3/16": 0.1875, "1/4": 0.25, "5/16": 0.3125,
    "3/8": 0.375, "1/2": 0.5, "5/8": 0.625, "3/4": 0.75, "7/8": 0.875,
}

# Gauge to simplified label for profile keys
_GAUGE_LABEL = {
    "7ga": "7ga", "10ga": "10ga", "11ga": "11ga", "14ga": "14ga",
    "16ga": "16ga", "18ga": "18ga", "20ga": "20ga", "22ga": "22ga",
}


def _parse_dimension(text: str) -> str:
    """Parse a dimension like '2\"', '1-1/2\"', '1/4\"' to a normalized string."""
    text = text.strip().rstrip('"\'')
    # Handle compound fractions: 1-1/2, 2-1/4, 1-3/4
    compound = re.match(r"(\d+)\s*-\s*(\d+)/(\d+)", text)
    if compound:
        whole = int(compound.group(1))
        num = int(compound.group(2))
        den = int(compound.group(3))
        val = whole + num / den
        return str(val) if val != int(val) else str(int(val))

    # Simple fraction: 1/2, 3/16, 1/4
    frac = re.match(r"^(\d+)/(\d+)$", text)
    if frac:
        val = int(frac.group(1)) / int(frac.group(2))
        return str(val) if val != int(val) else str(int(val))

    # Plain number
    try:
        val = float(text)
        return str(val) if val != int(val) else str(int(val))
    except ValueError:
        return text


def parse_profile_key(description: str) -> Optional[str]:
    """
    Parse a human-readable material description into an internal profile key.

    Examples:
        "Tubing - Square 2\" x 2\" x 11 ga"     -> "sq_tube_2x2_11ga"
        "Flat Bar - 1/4\" x 1\""                 -> "flat_bar_1x0.25"
        "Angle 2\" x 2\" x 3/16\""               -> "angle_2x2x0.1875"
        "2\" x 2\" x 11G HR SQUARE TUBE 24'"     -> "sq_tube_2x2_11ga"
        "Bar - Round 1/2\""                       -> "round_bar_0.5"
        "Tubing - Round 4\" OD x sch 40"         -> "pipe_4_sch40"
        "Channel 3\" x 4.1#"                     -> "channel_3x4.1"
    """
    desc = description.upper().strip()

    # Determine material type from description
    # Handle both "Square Tube" and Osorio's "Tubing - Square" formats
    is_tubing = "TUBE" in desc or "TUBING" in desc
    if ("SQUARE TUBE" in desc or "SQUARE TUBING" in desc or "SQ TUBE" in desc
            or (is_tubing and "SQUARE" in desc)):
        return _parse_tube_profile(desc, "sq_tube")
    if "RECT" in desc and is_tubing:
        return _parse_tube_profile(desc, "rect_tube")
    if ("ROUND TUBE" in desc or "ROUND TUBING" in desc or "RND TUBE" in desc
            or (is_tubing and "ROUND" in desc and "BAR" not in desc)):
        return _parse_round_tube_profile(desc)
    if re.search(r"(?:SCH|SCHEDULE)\s*\d+", desc) or "PIPE" in desc:
        return _parse_pipe_profile(desc)
    if "FLAT BAR" in desc or "FLAT" in desc and "BAR" in desc or "HR FLATS" in desc:
        return _parse_flat_bar_profile(desc)
    if "ANGLE" in desc:
        return _parse_angle_profile(desc)
    if "CHANNEL" in desc:
        return _parse_channel_profile(desc)
    if "ROUND" in desc and "BAR" in desc:
        return _parse_round_bar_profile(desc)
    if "SQUARE" in desc and "BAR" in desc:
        return _parse_sq_bar_profile(desc)
    if "SHEET" in desc or "PLATE" in desc:
        return None  # Sheets/plates handled differently (per sqft, not per foot)

    return None


def _parse_tube_profile(desc: str, prefix: str) -> Optional[str]:
    """Parse square or rectangular tube: 'sq_tube_2x2_11ga'."""
    # Extract dimensions: look for NxN or N" x N" patterns
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    gauge = _extract_gauge(desc)

    if len(dims) >= 2:
        d1 = _parse_dimension(dims[0])
        d2 = _parse_dimension(dims[1])
        if gauge:
            return f"{prefix}_{d1}x{d2}_{gauge}"
        # Check for wall thickness as 3rd dimension
        if len(dims) >= 3:
            thickness = dims[2]
            if "/" in thickness:
                return f"{prefix}_{d1}x{d2}_{_parse_dimension(thickness)}"
        return f"{prefix}_{d1}x{d2}"
    return None


def _parse_round_tube_profile(desc: str) -> Optional[str]:
    """Parse round tube: 'round_tube_1.5_11ga'."""
    # Look for OD dimension specifically: "1-1/2\" OD" or "4\" OD"
    od_match = re.search(
        r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']\s*OD",
        desc, re.IGNORECASE,
    )
    if od_match:
        d = _parse_dimension(od_match.group(1))
        gauge = _extract_gauge(desc)
        if gauge:
            return f"round_tube_{d}_{gauge}"
        return f"round_tube_{d}"

    # Fallback: first dimension in description (skip part numbers like 001800)
    # Only match dimensions that look reasonable (< 20)
    dims = re.findall(r"(?<!\d)(\d{1,2}(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']", desc)
    gauge = _extract_gauge(desc)
    if dims:
        d = _parse_dimension(dims[0])
        if gauge:
            return f"round_tube_{d}_{gauge}"
        return f"round_tube_{d}"
    return None


def _parse_pipe_profile(desc: str) -> Optional[str]:
    """Parse pipe: 'pipe_4_sch40'."""
    sch = re.search(r"(?:SCH|SCHEDULE)\s*(\d+)", desc)
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?\s*(?:OD)?", desc)
    if dims and sch:
        d = _parse_dimension(dims[0])
        return f"pipe_{d}_sch{sch.group(1)}"
    if dims:
        d = _parse_dimension(dims[0])
        return f"pipe_{d}"
    return None


def _parse_flat_bar_profile(desc: str) -> Optional[str]:
    """Parse flat bar: 'flat_bar_1x0.25'."""
    # Flat bar has thickness x width: "1/4\" x 1\""
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    if len(dims) >= 2:
        thickness = _parse_dimension(dims[0])
        width = _parse_dimension(dims[1])
        # Convention: flat_bar_{width}x{thickness}
        return f"flat_bar_{width}x{thickness}"
    return None


def _parse_angle_profile(desc: str) -> Optional[str]:
    """Parse angle: 'angle_2x2x0.1875'."""
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    if len(dims) >= 3:
        d1 = _parse_dimension(dims[0])
        d2 = _parse_dimension(dims[1])
        d3 = _parse_dimension(dims[2])
        return f"angle_{d1}x{d2}x{d3}"
    if len(dims) >= 2:
        d1 = _parse_dimension(dims[0])
        d2 = _parse_dimension(dims[1])
        return f"angle_{d1}x{d2}"
    return None


def _parse_channel_profile(desc: str) -> Optional[str]:
    """Parse channel: 'channel_3x4.1'."""
    # Channel can be "3\" x 4.1#" (size x weight/ft) or "2\" x 1\" x 1/8\""
    weight = re.search(r"(\d+(?:\.\d+)?)\s*#", desc)
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    if dims and weight:
        d = _parse_dimension(dims[0])
        return f"channel_{d}x{weight.group(1)}"
    if len(dims) >= 2:
        d1 = _parse_dimension(dims[0])
        d2 = _parse_dimension(dims[1])
        return f"channel_{d1}x{d2}"
    return None


def _parse_round_bar_profile(desc: str) -> Optional[str]:
    """Parse round bar: 'round_bar_0.5'."""
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    if dims:
        d = _parse_dimension(dims[0])
        return f"round_bar_{d}"
    return None


def _parse_sq_bar_profile(desc: str) -> Optional[str]:
    """Parse square bar: 'sq_bar_0.75'."""
    dims = re.findall(r"(\d+(?:\s*-\s*\d+/\d+|\s*/\s*\d+)?)\s*[\"']?", desc)
    if dims:
        d = _parse_dimension(dims[0])
        return f"sq_bar_{d}"
    return None


def _extract_gauge(desc: str) -> Optional[str]:
    """Extract gauge from description like '11ga', '14 ga', '11G'."""
    m = re.search(r"(\d+)\s*(?:GA|GAUGE|G)\b", desc, re.IGNORECASE)
    if m:
        return f"{m.group(1)}ga"
    # Check for fractional wall thickness: "x 1/8\"" at end could mean gauge
    # But we handle this separately in the profile parsers
    return None


# ---------------------------------------------------------------------------
# File-specific loaders
# ---------------------------------------------------------------------------

def load_osorio_prices(filepath: Path) -> dict:
    """
    Parse osorio_prices_seed.json → dict of profile_key → {price, supplier, date}.
    """
    prices = {}
    with open(filepath) as f:
        data = json.load(f)

    for item in data:
        material = item.get("material", "")
        price = item.get("price_per_foot")
        supplier = item.get("supplier", "Osorio")
        date = item.get("last_date", "")

        if price is None:
            continue

        # Check for stainless prefix
        is_stainless = material.upper().startswith("SS ")
        profile_key = parse_profile_key(material)

        if profile_key:
            # Prefix stainless keys
            if is_stainless and not profile_key.startswith("ss_"):
                profile_key = f"ss_304_{profile_key}"

            # Keep the most recent / highest quote_count price
            existing = prices.get(profile_key)
            if existing is None or item.get("quote_count", 0) > existing.get("quote_count", 0):
                prices[profile_key] = {
                    "price_per_foot": round(price, 4),
                    "supplier": supplier,
                    "date": date,
                    "quote_count": item.get("quote_count", 1),
                    "original_desc": material,
                }

    return prices


def load_wexler_prices(filepath: Path) -> dict:
    """
    Parse wexler_prices_raw.json → dict of profile_key → {price, supplier, date}.
    Only loads items priced per foot (unit == "ft").
    """
    prices = {}
    skipped_lb = 0

    with open(filepath) as f:
        data = json.load(f)

    for item in data:
        desc = item.get("description", "")
        unit = item.get("unit", "")
        rate = item.get("rate_per_unit")
        supplier = item.get("supplier", "Wexler")
        date = item.get("date", "")

        if rate is None:
            continue

        if unit != "ft":
            skipped_lb += 1
            continue

        profile_key = parse_profile_key(desc)
        if profile_key:
            # Keep the most recent price (by date)
            existing = prices.get(profile_key)
            if existing is None:
                prices[profile_key] = {
                    "price_per_foot": round(rate, 4),
                    "supplier": supplier,
                    "date": date,
                    "original_desc": desc,
                }
            else:
                # Compare dates — keep newer
                try:
                    existing_date = datetime.strptime(existing["date"], "%m/%d/%Y")
                    new_date = datetime.strptime(date, "%m/%d/%Y")
                    if new_date > existing_date:
                        prices[profile_key] = {
                            "price_per_foot": round(rate, 4),
                            "supplier": supplier,
                            "date": date,
                            "original_desc": desc,
                        }
                except (ValueError, TypeError):
                    pass  # Can't parse dates — keep existing

    if skipped_lb:
        print(f"    Skipped {skipped_lb} Wexler items priced per lb (not per foot)")

    return prices


def load_firetable_bom(filepath: Path) -> dict:
    """
    Parse firetable_pro_bom.json → dict of profile_key → {price, supplier, date}.
    Derives per-foot prices from unit prices and piece lengths.
    """
    prices = {}
    with open(filepath) as f:
        data = json.load(f)

    materials = data.get("materials", [])
    source = data.get("source_quote", "Osorio")

    for item in materials:
        desc = item.get("desc", "")
        unit_price = item.get("unit_price")
        if unit_price is None:
            continue

        # Extract length from description: "x 20'", "x 24'", "x 12'"
        length_match = re.search(r"(\d+)['\u2019]\s*$", desc)
        if not length_match:
            continue  # Can't derive per-foot price without length

        length_ft = int(length_match.group(1))
        if length_ft <= 0:
            continue

        price_per_foot = round(unit_price / length_ft, 4)

        # Parse profile key from description
        profile_key = parse_profile_key(desc)

        # Handle stainless
        mat_type = item.get("material", "")
        if "ss_304" in mat_type and profile_key and not profile_key.startswith("ss_"):
            profile_key = f"ss_304_{profile_key}"

        if profile_key:
            prices[profile_key] = {
                "price_per_foot": price_per_foot,
                "supplier": source,
                "date": "",
                "original_desc": desc,
            }

    return prices


def load_invoices_as_actuals(filepath: Path) -> list:
    """
    Parse createstage_invoices.json → list of HistoricalActual-ready dicts.
    Extracts whatever data is available from each invoice.
    """
    actuals = []
    with open(filepath) as f:
        data = json.load(f)

    for inv in data:
        invoice_num = inv.get("invoice", "")
        total = inv.get("total")
        material_cost = inv.get("material_cost")
        labor_cost = inv.get("labor_cost")
        hours_quoted = inv.get("hours_quoted")
        shop_rate = inv.get("shop_rate")
        date_str = inv.get("date", "")
        filename = inv.get("file", "")

        # Skip invoices with no useful data at all
        if total is None:
            continue

        # Build notes
        notes = f"Seeded from CreateStage invoice #{invoice_num}"
        if filename:
            notes += f" ({filename})"
        if date_str:
            notes += f" — {date_str}"

        # Build actual_hours_by_process
        # Most invoices don't have per-process breakdown; store what we have
        hours_by_process = None
        if hours_quoted is not None:
            # We only have total hours, not per-process
            hours_by_process = {"total_quoted": hours_quoted}
        elif labor_cost and shop_rate and shop_rate > 0:
            # Derive hours from labor_cost / shop_rate
            derived_hours = round(labor_cost / shop_rate, 1)
            hours_by_process = {"total_derived": derived_hours}
        elif labor_cost and labor_cost > 0:
            # Use default $125/hr to derive hours
            derived_hours = round(labor_cost / 125.0, 1)
            hours_by_process = {"total_derived": derived_hours}

        actuals.append({
            "quote_id": None,  # Pre-platform jobs, no quote record
            "actual_hours_by_process": hours_by_process,
            "actual_material_cost": material_cost,
            "notes": notes,
            "total_invoiced": total,
        })

    return actuals


# ---------------------------------------------------------------------------
# Merge and write seeded prices
# ---------------------------------------------------------------------------

def merge_prices(*price_dicts) -> dict:
    """
    Merge multiple price dicts. Later sources override earlier ones.
    Returns merged dict with profile_key → {price_per_foot, supplier, date}.
    """
    merged = {}
    for pd in price_dicts:
        for key, val in pd.items():
            existing = merged.get(key)
            if existing is None:
                merged[key] = val
            else:
                # Keep the one with more recent date, or higher quote_count
                try:
                    existing_date = datetime.strptime(existing.get("date", ""), "%m/%d/%Y")
                except (ValueError, TypeError):
                    existing_date = datetime.min
                try:
                    new_date = datetime.strptime(val.get("date", ""), "%m/%d/%Y")
                except (ValueError, TypeError):
                    new_date = datetime.min

                if new_date > existing_date:
                    merged[key] = val
                elif new_date == existing_date:
                    # Same date — prefer higher quote count
                    if val.get("quote_count", 0) > existing.get("quote_count", 0):
                        merged[key] = val
    return merged


def write_seeded_prices(prices: dict, output_path: Path) -> None:
    """Write merged prices to seeded_prices.json for MaterialLookup."""
    # Simplify to just profile_key → {price_per_foot, supplier}
    output = {}
    for key, val in sorted(prices.items()):
        output[key] = {
            "price_per_foot": val["price_per_foot"],
            "supplier": val.get("supplier", "unknown"),
        }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nWrote {len(output)} profile prices to {output_path}")


# ---------------------------------------------------------------------------
# Historical actuals DB loader
# ---------------------------------------------------------------------------

def load_actuals_to_db(actuals: list) -> int:
    """Load historical actuals into the database. Returns count loaded."""
    from backend.database import SessionLocal
    from backend import models

    if not actuals:
        return 0

    db = SessionLocal()
    count = 0
    try:
        for actual_data in actuals:
            # Skip if we have no cost data at all
            if (actual_data.get("actual_hours_by_process") is None and
                    actual_data.get("actual_material_cost") is None):
                continue

            actual = models.HistoricalActual(
                quote_id=actual_data.get("quote_id"),
                actual_hours_by_process=actual_data.get("actual_hours_by_process"),
                actual_material_cost=actual_data.get("actual_material_cost"),
                notes=actual_data.get("notes"),
                variance_pct=None,
                recorded_at=datetime.utcnow(),
            )
            db.add(actual)
            count += 1

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"  ERROR loading actuals: {e}")
        raise
    finally:
        db.close()

    return count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    raw_dir = Path(__file__).parent / "raw"
    data_dir = Path(__file__).parent
    print(f"Loading seed data from {raw_dir}...\n")

    if not raw_dir.exists():
        print(f"Directory {raw_dir} does not exist — nothing to load")
        return

    # --- Material prices ---
    all_prices = {}

    osorio_file = raw_dir / "osorio_prices_seed.json"
    if osorio_file.exists():
        print("Processing Osorio prices...")
        osorio_prices = load_osorio_prices(osorio_file)
        print(f"  {len(osorio_prices)} profile prices parsed from Osorio")
        all_prices = merge_prices(all_prices, osorio_prices)

    wexler_file = raw_dir / "wexler_prices_raw.json"
    if wexler_file.exists():
        print("Processing Wexler prices...")
        wexler_prices = load_wexler_prices(wexler_file)
        print(f"  {len(wexler_prices)} profile prices parsed from Wexler")
        all_prices = merge_prices(all_prices, wexler_prices)

    firetable_file = raw_dir / "firetable_pro_bom.json"
    if firetable_file.exists():
        print("Processing FireTable BOM...")
        ft_prices = load_firetable_bom(firetable_file)
        print(f"  {len(ft_prices)} profile prices derived from FireTable BOM")
        all_prices = merge_prices(all_prices, ft_prices)

    # Write merged prices
    if all_prices:
        output_path = data_dir / "seeded_prices.json"
        write_seeded_prices(all_prices, output_path)
    else:
        print("\nNo material prices to write.")

    # --- Historical actuals ---
    invoices_file = raw_dir / "createstage_invoices.json"
    if invoices_file.exists():
        print("\nProcessing CreateStage invoices...")
        actuals = load_invoices_as_actuals(invoices_file)
        print(f"  {len(actuals)} invoices parsed")

        actuals_with_data = [a for a in actuals
                             if a.get("actual_hours_by_process") or a.get("actual_material_cost")]
        if actuals_with_data:
            count = load_actuals_to_db(actuals_with_data)
            print(f"  {count} historical actuals loaded to database")
        else:
            print("  No invoices with labor/material breakdown — skipping DB load")
            print("  (Invoices have total cost only; add per-process hours for full loading)")

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Material profiles with real prices: {len(all_prices)}")
    if all_prices:
        suppliers = set(v.get("supplier", "?") for v in all_prices.values())
        print(f"Suppliers: {', '.join(sorted(suppliers))}")
    print("Done.")


if __name__ == "__main__":
    main()
