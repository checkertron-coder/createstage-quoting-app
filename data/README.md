# Data Seed Directory

This directory holds invoice/pricing data that feeds into the quoting app's material prices and historical labor actuals.

## How to add data

1. Process invoices/quotes into JSON format (see schema below)
2. Save JSON files into `data/raw/`
3. Run: `python data/seed_from_invoices.py`

## JSON Schema — Material Prices

Each file in `data/raw/` should contain one or more records:

```json
[
    {
        "material_type": "sq_tube_2x11ga",
        "price_per_foot": 3.45,
        "price_per_lb": null,
        "price_per_sqft": null,
        "supplier": "Osorio",
        "date": "2024-03-15",
        "notes": "Invoice #12345"
    }
]
```

Single records (not in an array) are also accepted:

```json
{
    "material_type": "flat_bar_1x14ga",
    "price_per_foot": 1.25,
    "supplier": "Wexler",
    "date": "2024-06-01"
}
```

## JSON Schema — Labor Actuals

Files with `"type": "labor_actual"` are loaded into the historical_actuals table:

```json
{
    "type": "labor_actual",
    "quote_id": 42,
    "actual_hours_by_process": {
        "layout_setup": 1.5,
        "cut_prep": 2.0,
        "fit_tack": 3.0,
        "full_weld": 4.0,
        "grind_clean": 1.5
    },
    "actual_material_cost": 450.00,
    "notes": "Swing gate job, 6ft double panel"
}
```

## Important

- `data/raw/` is gitignored — actual invoice data stays local
- The seed script is non-destructive: newer prices override older ones, existing data is never deleted
- Files are processed alphabetically; name them with dates for predictable ordering (e.g., `2024-03-15_osorio.json`)
