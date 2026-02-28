"""
Bid Document Parser — Enterprise Feature (Session 7).

Extracts metal fabrication scope from construction bid documents.
A fabricator receives a 50-300 page PDF from a general contractor.
The parser reads it, finds metal fab line items (railings, gates, stairs,
structural connections), and presents them as separate quotable jobs
that feed into the existing pipeline.

Uses Gemini 2.0 Flash for extraction with keyword-based fallback.
"""

import json
import logging
import math
import os
import re
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)


# CSI divisions relevant to metal fabrication
RELEVANT_CSI_DIVISIONS = {
    "05": "Metals",
    "05 12 00": "Structural Steel Framing",
    "05 21 00": "Steel Joist Framing",
    "05 31 00": "Steel Decking",
    "05 50 00": "Metal Fabrications",
    "05 51 00": "Metal Stairs",
    "05 52 00": "Metal Railings",
    "05 52 13": "Pipe and Tube Railings",
    "05 53 00": "Metal Gratings",
    "05 56 00": "Metal Castings",
    "05 58 00": "Formed Metal Fabrications",
    "05 70 00": "Decorative Metal",
    "05 71 00": "Decorative Metal Stairs",
    "05 73 00": "Decorative Metal Railings",
    "08 34 00": "Special Function Doors",
    "10 73 00": "Protective Covers",
    "32 31 00": "Fences and Gates",
}

# Keywords that indicate metal fab scope
EXTRACTION_KEYWORDS = [
    "railing", "handrail", "guardrail", "balustrade",
    "gate", "fence", "fencing",
    "stair", "staircase", "stringer", "tread",
    "bollard",
    "structural steel", "misc metals", "miscellaneous metals",
    "metal fabrication", "ornamental iron", "wrought iron",
    "embed plate", "base plate", "connection plate",
    "canopy", "awning",
    "mezzanine", "platform",
    "ladder", "ship's ladder",
    "enclosure", "equipment screen",
    "welded", "fabricated steel",
]

# Job type mapping keywords
_JOB_TYPE_KEYWORDS = {
    "cantilever_gate": ["cantilever gate", "sliding gate", "cantilever sliding"],
    "swing_gate": ["swing gate", "hinged gate", "swinging gate", "pedestrian gate"],
    "straight_railing": [
        "railing", "handrail", "guardrail", "pipe railing",
        "tube railing", "iron railing", "metal railing",
    ],
    "stair_railing": [
        "stair railing", "stair handrail", "stairway railing",
        "ornamental iron railing",
    ],
    "ornamental_fence": ["fence", "fencing", "ornamental fence", "iron fence"],
    "complete_stair": [
        "steel stair", "metal stair", "staircase", "stringer",
        "stair with", "provide steel stair",
    ],
    "spiral_stair": ["spiral stair", "spiral staircase", "helical stair"],
    "window_security_grate": ["security grate", "window grate", "security bar", "window guard"],
    "balcony_railing": ["balcony railing", "balcony guardrail"],
    "bollard": ["bollard"],
    "utility_enclosure": [
        "enclosure", "equipment screen", "dumpster enclosure",
        "mechanical screen",
    ],
    "repair_structural": ["structural repair", "weld repair"],
    "repair_decorative": ["ornamental repair", "decorative repair"],
    "furniture_table": ["steel table", "metal table", "steel bench"],
    "custom_fab": [
        "misc metals", "miscellaneous metals", "embed plate",
        "base plate", "connection plate", "canopy", "awning",
        "mezzanine", "platform", "ladder", "ship's ladder",
    ],
}

# Dimension patterns
_DIM_PATTERNS = [
    # 12'-0", 16'-6"
    re.compile(r"(\d+)['\u2019]\s*-?\s*(\d+)\s*[\"'\u201d]?", re.IGNORECASE),
    # 42", 36"
    re.compile(r"(\d+)\s*(?:inches|inch|in\.|\"|\u201d)", re.IGNORECASE),
    # 16', 20'
    re.compile(r"(\d+)\s*(?:feet|foot|ft\.|['\u2019])", re.IGNORECASE),
    # 65 LF, 120 linear feet
    re.compile(r"(\d+)\s*(?:LF|linear\s*(?:feet|foot|ft))", re.IGNORECASE),
]

# CSI code pattern: 05 50 00 or 05 52 13 or 053100
_CSI_PATTERN = re.compile(r"\b(\d{2})\s+(\d{2})\s+(\d{2})\b")
_CSI_PATTERN_COMPACT = re.compile(r"\b(\d{2})(\d{2})(\d{2})\b")


class BidParser:
    """
    Extracts metal fabrication scope from construction bid documents.

    Input: Raw text from a PDF (extracted via pdfplumber or similar)
    Output: List of extracted scope items, each mapped to a job type
    """

    def parse_document(self, text: str, filename: str = "") -> dict:
        """
        Main entry point.

        Args:
            text: Full text content extracted from the bid document
            filename: Original filename for reference

        Returns dict with filename, items, warnings, confidence, etc.
        """
        if not text or not text.strip():
            return {
                "filename": filename,
                "total_pages_approx": 0,
                "extraction_confidence": 0.0,
                "items": [],
                "skipped_sections": [],
                "warnings": ["Document is empty — no text to parse."],
            }

        # Approximate page count (avg ~3000 chars per page)
        total_pages_approx = max(1, math.ceil(len(text) / 3000))

        # Try Gemini extraction first, fall back to keyword-based
        items = self._extract_with_gemini(text)
        extraction_method = "gemini"
        if not items:
            items = self._extract_with_keywords(text)
            extraction_method = "keyword"

        # Map job types and pre-populate fields
        for item in items:
            if not item.get("job_type"):
                item["job_type"] = self._map_to_job_type(
                    item.get("description", ""),
                    source_text=item.get("source_text", ""),
                )
            item["pre_populated_fields"] = self._pre_populate_fields(item)

        # Calculate overall confidence
        extraction_confidence = self._calculate_confidence(items, len(text))

        # Build warnings
        warnings = []
        if extraction_method == "keyword":
            warnings.append(
                "Extraction used keyword-based fallback (AI unavailable). "
                "Results may be less accurate."
            )
        if not items:
            warnings.append(
                "No metal fabrication scope items found in this document."
            )
        vague_items = [i for i in items if (i.get("confidence", 0) or 0) < 0.5]
        if vague_items:
            warnings.append(
                f"{len(vague_items)} item(s) have low confidence and may need "
                f"manual verification."
            )

        # Identify skipped sections (CSI divisions found but not metal fab)
        skipped = self._find_skipped_sections(text)

        return {
            "filename": filename,
            "total_pages_approx": total_pages_approx,
            "extraction_confidence": extraction_confidence,
            "items": items,
            "skipped_sections": skipped,
            "warnings": warnings,
        }

    def _extract_with_gemini(self, text: str) -> list:
        """
        Send document text to Gemini for scope extraction.
        Returns list of ExtractedItem dicts.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        if not api_key:
            logger.warning("No GEMINI_API_KEY — using keyword-based fallback for bid parsing")
            return []

        # Truncate text if too long (Gemini context limit ~1M tokens)
        # For safety, cap at ~200k chars (~50k tokens)
        max_chars = 200_000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[DOCUMENT TRUNCATED — remaining pages not analyzed]"

        prompt = self._build_extraction_prompt(text)

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
            f":generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                result = json.loads(response.read())
                response_text = result["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(response_text)

                # Normalize: could be a list or {"items": list}
                if isinstance(parsed, dict) and "items" in parsed:
                    raw_items = parsed["items"]
                elif isinstance(parsed, list):
                    raw_items = parsed
                else:
                    return []

                return [self._normalize_item(item) for item in raw_items if item]
        except Exception as e:
            logger.warning(f"Gemini bid extraction failed: {e}")
            return []

    def _build_extraction_prompt(self, text: str) -> str:
        """Build the Gemini prompt for bid document scope extraction."""
        return f"""You are analyzing a construction bid document for a metal fabricator.

TASK: Extract ALL metal fabrication scope items from this document. These include:
- Railings, handrails, guardrails (pipe, tube, ornamental iron)
- Gates (cantilever sliding, swing, pedestrian, driveway)
- Fences and fencing (ornamental iron, steel picket)
- Stairs and staircases (steel stringers, treads, landings)
- Bollards (fixed, removable)
- Miscellaneous metals (embed plates, connection brackets, support angles)
- Enclosures and screens (equipment, dumpster, mechanical)
- Canopies, awnings, mezzanines, platforms, ladders

GUIDELINES:
- Metal fabrication items are typically in CSI Division 05 (Metals), but may appear in Division 32 (Site Improvements - fences/gates), Division 08 (Openings - security grates), or Division 10 (Specialties).
- Look for specific callouts: "ornamental iron", "misc metals", "metal fabrications", "welded steel", "handrail", "guardrail".
- Extract dimensions when given (width, height, linear footage, number of risers, clear opening).
- Note drawing references (e.g., "See Detail A-12", "Dwg S-301") - these are critical for the fabricator.
- If a section mentions "metal fabrications" without specifics, extract it with a note that it needs clarification. Do NOT skip vague items - flag them.

CONFIDENCE SCORING:
- 1.0 = specific dimensions AND material specified
- 0.8 = specific dimensions but no material
- 0.7 = description clear but no dimensions
- 0.5 = vague reference to metal fab scope
- 0.3 = implied but not explicitly stated

Return a JSON array of items. Each item must have:
- "description": string (what the item is, plain language)
- "location": string or null (where in the building, e.g., "Stair 1", "Parking Level 2")
- "csi_division": string or null (CSI code if found, e.g., "05 52 00")
- "dimensions": object or null (any dimensions: width, height, linear_footage, clear_opening, rise, run, etc.)
- "material_spec": string or null (material if specified, e.g., "1.5 in sq tube", "ASTM A500 Grade B")
- "quantity": integer or null (number of units if specified)
- "detail_reference": string or null (drawing reference like "Detail A-12", "Dwg S-301")
- "confidence": float (0.0-1.0)
- "source_text": string (the original text snippet, max 200 chars)

DOCUMENT TEXT:
\"\"\"
{text}
\"\"\"

Return ONLY valid JSON array:"""

    def _normalize_item(self, raw: dict) -> dict:
        """Normalize a raw Gemini-extracted item to the ExtractedItem schema."""
        return {
            "description": str(raw.get("description", "")).strip(),
            "job_type": raw.get("job_type"),  # Usually None from Gemini; we map later
            "location": raw.get("location"),
            "csi_division": raw.get("csi_division"),
            "dimensions": raw.get("dimensions"),
            "material_spec": raw.get("material_spec"),
            "quantity": _safe_int(raw.get("quantity")),
            "detail_reference": raw.get("detail_reference"),
            "confidence": _safe_float(raw.get("confidence"), default=0.5),
            "source_text": str(raw.get("source_text", ""))[:200],
            "pre_populated_fields": {},
        }

    def _extract_with_keywords(self, text: str) -> list:
        """
        Fallback: regex/keyword-based extraction when Gemini is unavailable.
        Splits text into sections, scores by keyword density, extracts dimensions.
        """
        items = []

        # Split into sections by common spec headings
        sections = self._split_into_sections(text)

        # Non-scope section titles — these are administrative/reference, not actual work
        _SKIP_TITLES = {
            "summary", "references", "submittals", "related sections",
            "quality assurance", "delivery", "storage", "warranty",
            "general", "materials", "products", "fasteners",
            "definitions", "design criteria", "performance requirements",
        }

        for section_title, section_text in sections:
            # Skip administrative sections (Parts 1 & 2 of specs)
            title_lower = section_title.lower()
            if any(skip in title_lower for skip in _SKIP_TITLES):
                continue

            # Score section by keyword density
            score = self._keyword_score(section_text)
            if score < 0.5:
                continue

            # Extract CSI code from section title or text
            csi = self._extract_csi_code(section_title + " " + section_text)

            # Extract dimensions
            dimensions = self._extract_dimensions(section_text)

            # Extract material spec
            material_spec = self._extract_material_spec(section_text)

            # Extract detail references
            detail_ref = self._extract_detail_reference(section_text)

            # Extract quantity
            quantity = self._extract_quantity(section_text)

            # Build description from section title
            description = section_title.strip()
            if not description:
                # Use first meaningful line
                for line in section_text.split("\n"):
                    line = line.strip()
                    if len(line) > 10 and any(kw in line.lower() for kw in EXTRACTION_KEYWORDS):
                        description = line[:120]
                        break
            if not description:
                description = section_text[:120].strip()

            # Confidence based on what we extracted
            confidence = 0.3
            if csi and csi.startswith("05"):
                confidence += 0.2
            if dimensions:
                confidence += 0.2
            if material_spec:
                confidence += 0.1
            if detail_ref:
                confidence += 0.1
            confidence = min(confidence, 1.0)

            items.append({
                "description": description,
                "job_type": None,  # Mapped later
                "location": self._extract_location(section_text),
                "csi_division": csi,
                "dimensions": dimensions if dimensions else None,
                "material_spec": material_spec,
                "quantity": quantity,
                "detail_reference": detail_ref,
                "confidence": round(confidence, 2),
                "source_text": section_text[:200],
                "pre_populated_fields": {},
            })

        return items

    def _split_into_sections(self, text: str) -> list:
        """Split document text into (title, body) sections."""
        # Pattern matches spec sections like "3.01 STAIR 1" or "SECTION 05 50 00"
        # Use [ \t] instead of \s to avoid matching across newlines in section titles
        section_pattern = re.compile(
            r"(?:^|\n)[ \t]*(?:SECTION[ \t]+)?(\d+(?:\.\d+)?(?:[ \t]+\d{2}[ \t]+\d{2})?[ \t]*[—\-]?[ \t]*[A-Z][A-Z \t\d,/\-—]*)",
            re.MULTILINE,
        )
        matches = list(section_pattern.finditer(text))

        sections = []
        for i, match in enumerate(matches):
            title = match.group(0).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((title, body))

        # If no sections found, treat entire text as one section
        if not sections:
            sections = [("", text)]

        return sections

    def _keyword_score(self, text: str) -> float:
        """Score a text section by keyword density (count per 100 words)."""
        text_lower = text.lower()
        words = text_lower.split()
        if not words:
            return 0.0

        keyword_count = sum(1 for kw in EXTRACTION_KEYWORDS if kw in text_lower)
        # Score: keywords per 100 words, capped at 10
        score = min(keyword_count / max(len(words) / 100, 1), 10.0)
        return score

    def _extract_csi_code(self, text: str) -> Optional[str]:
        """Extract CSI division code from text."""
        match = _CSI_PATTERN.search(text)
        if match:
            code = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            return code
        match = _CSI_PATTERN_COMPACT.search(text)
        if match:
            code = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            return code
        return None

    def _extract_dimensions(self, text: str) -> dict:
        """Extract dimensions from text using regex patterns."""
        dims = {}

        # Linear footage: "65 LF", "120 linear feet"
        lf_match = re.search(
            r"(\d+)\s*(?:LF|linear\s*(?:feet|foot|ft))",
            text, re.IGNORECASE,
        )
        if lf_match:
            dims["linear_footage"] = lf_match.group(1)

        # Clear opening: "16'-0"", "clear opening: 16'"
        opening_match = re.search(
            r"clear\s*opening[:\s]*(\d+)['\u2019]\s*-?\s*(\d*)[\"'\u201d]?",
            text, re.IGNORECASE,
        )
        if opening_match:
            feet = int(opening_match.group(1))
            inches = int(opening_match.group(2)) if opening_match.group(2) else 0
            dims["clear_width"] = str(feet) if inches == 0 else f"{feet}'{inches}\""

        # Height: "42" high", "height: 6'-0""
        height_match = re.search(
            r"height[:\s]*(\d+)['\u2019]\s*-?\s*(\d*)[\"'\u201d]?",
            text, re.IGNORECASE,
        )
        if height_match:
            feet = int(height_match.group(1))
            inches = int(height_match.group(2)) if height_match.group(2) else 0
            if feet <= 10:  # Likely feet
                dims["height"] = str(feet)
            else:  # Likely inches (42" = 42 inches)
                dims["height"] = f'{feet}"'

        # Height in inches: "42" high", "42 inches"
        height_in_match = re.search(
            r"(\d+)\s*(?:inches|\"|\u201d)\s*(?:high|tall|height)",
            text, re.IGNORECASE,
        )
        if height_in_match and "height" not in dims:
            dims["height"] = f'{height_in_match.group(1)}"'

        # Width: "width: 44"", "44\" clear"
        width_match = re.search(
            r"width[:\s]*(\d+)\s*(?:inches|\"|\u201d|['\u2019])",
            text, re.IGNORECASE,
        )
        if width_match:
            dims["width"] = f'{width_match.group(1)}"'

        # Total rise: "total rise: 12'-0""
        rise_match = re.search(
            r"(?:total\s*)?rise[:\s]*(\d+)['\u2019]\s*-?\s*(\d*)[\"'\u201d]?",
            text, re.IGNORECASE,
        )
        if rise_match:
            feet = int(rise_match.group(1))
            inches = int(rise_match.group(2)) if rise_match.group(2) else 0
            dims["total_rise"] = f"{feet}'" if inches == 0 else f"{feet}'-{inches}\""

        # Above grade: "36\" above grade"
        above_match = re.search(
            r"(\d+)\s*(?:inches|\"|\u201d)\s*above\s*grade",
            text, re.IGNORECASE,
        )
        if above_match:
            dims["height_above_grade"] = f'{above_match.group(1)}"'

        return dims

    def _extract_material_spec(self, text: str) -> Optional[str]:
        """Extract material specification from text."""
        specs = []

        # ASTM specs
        astm_match = re.findall(r"ASTM\s+[A-Z]\d+(?:\s*,?\s*(?:Grade|Type)\s+[A-Z\d]+)?", text)
        specs.extend(astm_match)

        # Tube/pipe sizes: "2\" square tube", "1.5\" OD", "6\" schedule 40"
        tube_match = re.findall(
            r"\d+(?:\.\d+)?(?:\s*-?\s*\d+/\d+)?\s*(?:\"|\u201d|inch)\s*"
            r"(?:square\s*tube|sq\s*tube|round\s*tube|pipe|OD|schedule\s*\d+)",
            text, re.IGNORECASE,
        )
        specs.extend(tube_match)

        # Stainless steel: "304 SS", "Type 304", "stainless steel"
        ss_match = re.findall(
            r"(?:AISI\s+)?(?:Type\s+)?(?:304|316)\s*(?:SS|stainless)?|stainless\s+steel",
            text, re.IGNORECASE,
        )
        specs.extend(ss_match)

        if specs:
            return "; ".join(specs[:3])  # Return up to 3 specs
        return None

    def _extract_detail_reference(self, text: str) -> Optional[str]:
        """Extract drawing/detail references from text."""
        patterns = [
            re.compile(r"(?:See\s+)?Detail\s+[A-Z][\-/]?\d+", re.IGNORECASE),
            re.compile(r"(?:See\s+)?(?:Dwg|Drawing)\s+[A-Z][\-/]?\d+", re.IGNORECASE),
            re.compile(r"(?:See\s+)?[Ss]heet(?:s)?\s+[A-Z][\-/]?\d+", re.IGNORECASE),
        ]
        refs = []
        for p in patterns:
            for m in p.finditer(text):
                refs.append(m.group(0).strip())
        return "; ".join(refs) if refs else None

    def _extract_quantity(self, text: str) -> Optional[int]:
        """Extract quantity from text like '(6) bollards' or 'provide 4 gates'."""
        qty_match = re.search(
            r"(?:provide\s+)?(?:\((\d+)\)|(\d+)\s+(?:ea|each|units?|pieces?))\s",
            text, re.IGNORECASE,
        )
        if qty_match:
            return int(qty_match.group(1) or qty_match.group(2))

        # Pattern: "(6) fixed bollards"
        paren_match = re.search(r"\((\d+)\)\s+\w+", text)
        if paren_match:
            return int(paren_match.group(1))

        return None

    def _extract_location(self, text: str) -> Optional[str]:
        """Extract location/area from text."""
        patterns = [
            re.compile(r"(?:at|for|@)\s+((?:Stair|Level|Floor|Parking|Entrance|Lobby|"
                        r"Main|Ground|Second|Third|Roof|Basement|Storefront|Loading)"
                        r"[\w\s\-]*\d*)", re.IGNORECASE),
            re.compile(r"(Stair\s+\d+[A-Z]?)", re.IGNORECASE),
            re.compile(r"((?:Ground|First|Second|Third|Fourth)\s+Floor)", re.IGNORECASE),
            re.compile(r"(Level\s+\d+)", re.IGNORECASE),
        ]
        for p in patterns:
            m = p.search(text)
            if m:
                return m.group(1).strip()
        return None

    def _map_to_job_type(self, description: str, source_text: str = "") -> Optional[str]:
        """
        Maps an extracted item description to a V2 job type.
        Checks both the description (section title) and source_text (section body).
        Returns None if the item doesn't match any known type.
        """
        # Combine description and source_text for matching —
        # section titles are often short ("STAIR 1") while the body
        # contains the actual keywords ("Provide steel stair...")
        combined = (description + " " + source_text).lower()

        # Check specific types first (more specific patterns before generic)
        type_priority = [
            "spiral_stair",
            "cantilever_gate",
            "swing_gate",
            "stair_railing",
            "balcony_railing",
            "window_security_grate",
            "complete_stair",
            "bollard",
            "utility_enclosure",
            "ornamental_fence",
            "repair_structural",
            "repair_decorative",
            "furniture_table",
            "straight_railing",  # Generic railing last (catches "railing" broadly)
            "custom_fab",        # Catch-all last
        ]

        for job_type in type_priority:
            keywords = _JOB_TYPE_KEYWORDS.get(job_type, [])
            for kw in keywords:
                if kw in combined:
                    return job_type

        return None

    def _pre_populate_fields(self, item: dict) -> dict:
        """
        Map extracted dimensions/specs to question tree field IDs.
        """
        fields = {}
        dims = item.get("dimensions") or {}
        job_type = item.get("job_type")

        if not job_type:
            return fields

        # Gate types
        if job_type in ("cantilever_gate", "swing_gate"):
            if "clear_width" in dims:
                fields["clear_width"] = dims["clear_width"]
            if "height" in dims:
                fields["height"] = dims["height"]

        # Railing types
        if job_type in ("straight_railing", "stair_railing", "balcony_railing"):
            if "linear_footage" in dims:
                fields["linear_footage"] = dims["linear_footage"]
            if "height" in dims:
                fields["railing_height"] = dims["height"]

        # Complete stair
        if job_type == "complete_stair":
            if "total_rise" in dims:
                fields["total_rise"] = dims["total_rise"]
            if "width" in dims:
                fields["stair_width"] = dims["width"]

        # Bollard
        if job_type == "bollard":
            if "height_above_grade" in dims:
                fields["height"] = dims["height_above_grade"]
            qty = item.get("quantity")
            if qty:
                fields["quantity"] = str(qty)

        # Material spec → frame_material if applicable
        material_spec = item.get("material_spec")
        if material_spec:
            spec_lower = material_spec.lower()
            if "square tube" in spec_lower or "sq tube" in spec_lower:
                fields["frame_material"] = "Square tube (most common)"
            elif "round tube" in spec_lower or "pipe" in spec_lower:
                fields["frame_material"] = "Round tube / pipe"

        # Finish
        source = item.get("source_text", "").lower() + " " + item.get("description", "").lower()
        if "powder coat" in source:
            fields["finish"] = "Powder coat (most durable, outsourced)"
        elif "galvanize" in source or "galvanized" in source or "hot-dip" in source:
            fields["finish"] = "Hot-dip galvanized (outsourced)"
        elif "paint" in source:
            fields["finish"] = "Paint (in-house)"

        return fields

    def _calculate_confidence(self, items: list, text_length: int) -> float:
        """
        Estimate overall extraction confidence.
        Higher if: clear CSI divisions, specific dimensions, multiple items corroborate.
        Lower if: vague descriptions, no dimensions, ambiguous scope.
        """
        if not items:
            return 0.0

        # Average item confidence
        avg_confidence = sum(i.get("confidence", 0) for i in items) / len(items)

        # Boost if multiple items found (cross-corroboration)
        count_bonus = min(len(items) * 0.05, 0.15)

        # Boost if CSI codes found
        csi_count = sum(1 for i in items if i.get("csi_division"))
        csi_bonus = min(csi_count * 0.05, 0.1)

        # Boost if dimensions found
        dim_count = sum(1 for i in items if i.get("dimensions"))
        dim_bonus = min(dim_count * 0.05, 0.1)

        confidence = avg_confidence + count_bonus + csi_bonus + dim_bonus
        return round(min(confidence, 1.0), 2)

    def _find_skipped_sections(self, text: str) -> list:
        """Find CSI sections that were in the document but aren't metal fab."""
        skipped = []
        # Look for SECTION XX XX XX patterns
        for m in _CSI_PATTERN.finditer(text):
            code = f"{m.group(1)} {m.group(2)} {m.group(3)}"
            div = m.group(1)
            if div not in ("05", "08", "10", "32"):
                # Not a metal fab division — note it
                skipped.append(code)
        return list(set(skipped))[:10]  # Cap at 10


def _safe_int(val) -> Optional[int]:
    """Convert to int safely, return None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val, default=0.5) -> float:
    """Convert to float safely, return default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
