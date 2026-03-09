# PROMPT 40 — "Aluminum Validation Fix"

## PROBLEM
`VALID_PROFILES` in `backend/knowledge/validation.py` only contains steel profile keys. Aluminum profiles (al_sheet_*, al_sq_tube_*, al_flat_bar_*, al_angle_*, al_rect_tube_*, al_round_tube_*) were added to `material_lookup.py` in P38 but never added to the validation whitelist. This causes every aluminum cut list item to show "[WARNING] Unrecognized profile" even though prices resolve correctly.

## FIX
In `backend/knowledge/validation.py`, add ALL aluminum profiles from `material_lookup.py` to the `VALID_PROFILES` set.

Add these profiles:
```python
# Aluminum tube — 6061-T6
"al_sq_tube_1x1_0.125", "al_sq_tube_1.5x1.5_0.125", "al_sq_tube_2x2_0.125",
"al_rect_tube_1x2_0.125",
# Aluminum angle — 6061-T6
"al_angle_1.5x1.5x0.125", "al_angle_2x2x0.125",
# Aluminum flat bar — 6061-T6
"al_flat_bar_1x0.125", "al_flat_bar_1.5x0.125", "al_flat_bar_2x0.25",
# Aluminum round tube — 6061-T6
"al_round_tube_1.5_0.125",
# Aluminum sheet — 5052-H32 / 6061-T6
"al_sheet_0.040", "al_sheet_0.063", "al_sheet_0.080", "al_sheet_0.125", "al_sheet_0.190",
```

Also: to prevent this from happening again, add a test that verifies every key in `material_lookup.py`'s PRICE_PER_FOOT dict is also in VALID_PROFILES (or explicitly excluded).

## ALSO VERIFY
Confirm that the P39 changes (electronics keyword detection in `quote_session.py`) are committed and deployed. The electronics question injection should fire for any description mentioning LED, ESP32, controller, etc. — even when all tree questions are already answered.

## RUN
`pytest tests/` — all must pass. Then `git add . && git commit -m "P40: Add aluminum profiles to VALID_PROFILES" && git push`
