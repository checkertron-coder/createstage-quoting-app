#!/usr/bin/env python3
"""
Seed material prices and historical labor actuals from invoice JSON files.

Usage:
    python data/seed_from_invoices.py

Reads all *.json files from data/raw/, inserts or updates the database.
Non-destructive: never deletes existing data, only adds or updates.

See data/README.md for JSON format.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.database import SessionLocal
from backend import models


def load_json_files(raw_dir: Path) -> list[dict]:
    """Load and parse all .json files from raw_dir, sorted alphabetically."""
    records = []
    if not raw_dir.exists():
        print(f"Directory {raw_dir} does not exist — nothing to load")
        return records

    json_files = sorted(raw_dir.glob("*.json"))
    if not json_files:
        print(f"No .json files found in {raw_dir}")
        return records

    for filepath in json_files:
        try:
            with open(filepath) as f:
                data = json.load(f)
            # Normalize: wrap single records in a list
            if isinstance(data, dict):
                data = [data]
            for record in data:
                record["_source_file"] = filepath.name
            records.extend(data)
            print(f"  Loaded {len(data)} record(s) from {filepath.name}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ERROR reading {filepath.name}: {e}")

    return records


def seed_material_price(db, record: dict) -> str:
    """Insert or update a material price record. Returns 'added', 'updated', or 'skipped'."""
    material_type = record.get("material_type")
    if not material_type:
        return "skipped"

    record_date_str = record.get("date")
    record_date = datetime.fromisoformat(record_date_str) if record_date_str else datetime.utcnow()

    # Check for existing record by material_type
    # DECISION: Using string match on material_type since v2 material prices may expand
    # beyond the current MaterialType enum. For now, try to match enum; if no match,
    # look for a string-based entry.
    existing = None
    try:
        mat_enum = models.MaterialType(material_type)
        existing = db.query(models.MaterialPrice).filter(
            models.MaterialPrice.material_type == mat_enum
        ).first()
    except ValueError:
        # material_type doesn't match the enum — skip for now
        # In v2, when material_prices uses VARCHAR, this will work for all types
        print(f"    Warning: '{material_type}' is not in MaterialType enum — skipping")
        return "skipped"

    price_per_foot = record.get("price_per_foot")
    price_per_lb = record.get("price_per_lb")
    price_per_sqft = record.get("price_per_sqft")
    notes = record.get("notes", "")
    supplier = record.get("supplier", "")
    if supplier:
        notes = f"{supplier} — {notes}" if notes else supplier

    if existing:
        # Only update if the new record is newer
        if existing.updated_at and record_date <= existing.updated_at:
            return "skipped"
        if price_per_foot is not None:
            existing.price_per_foot = price_per_foot
        if price_per_lb is not None:
            existing.price_per_lb = price_per_lb
        if price_per_sqft is not None:
            existing.price_per_sqft = price_per_sqft
        existing.notes = notes
        existing.updated_at = record_date
        return "updated"
    else:
        new_price = models.MaterialPrice(
            material_type=mat_enum,
            price_per_foot=price_per_foot,
            price_per_lb=price_per_lb,
            price_per_sqft=price_per_sqft,
            notes=notes,
            updated_at=record_date,
        )
        db.add(new_price)
        return "added"


def seed_labor_actual(db, record: dict) -> str:
    """Insert a historical labor actual record. Returns 'added' or 'skipped'."""
    actual_hours = record.get("actual_hours_by_process")
    if not actual_hours:
        return "skipped"

    quote_id = record.get("quote_id")
    actual = models.HistoricalActual(
        quote_id=quote_id,
        actual_hours_by_process=actual_hours,
        actual_material_cost=record.get("actual_material_cost"),
        notes=record.get("notes"),
        variance_pct=record.get("variance_pct"),
        recorded_at=datetime.utcnow(),
    )
    db.add(actual)
    return "added"


def main():
    raw_dir = Path(__file__).parent / "raw"
    print(f"Loading invoice data from {raw_dir}...")

    records = load_json_files(raw_dir)
    if not records:
        print("No records to process. Done.")
        return

    db = SessionLocal()
    try:
        material_stats = {"added": 0, "updated": 0, "skipped": 0}
        labor_stats = {"added": 0, "skipped": 0}

        for record in records:
            if record.get("type") == "labor_actual":
                result = seed_labor_actual(db, record)
                labor_stats[result] = labor_stats.get(result, 0) + 1
            else:
                result = seed_material_price(db, record)
                material_stats[result] = material_stats.get(result, 0) + 1

        db.commit()

        print(f"\nMaterial prices: {material_stats['added']} added, "
              f"{material_stats['updated']} updated, "
              f"{material_stats['skipped']} already current")
        print(f"Labor actuals: {labor_stats['added']} added, "
              f"{labor_stats['skipped']} skipped")
        print("Done.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
