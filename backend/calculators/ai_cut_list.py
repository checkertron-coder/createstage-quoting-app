"""
AI-assisted cut list generator for custom/complex jobs.

Uses Gemini to interpret freeform designs into detailed cut lists.
Called by calculators that handle custom or non-standard designs
(furniture_table, custom_fab, furniture_other, led_sign_custom,
repair_decorative, repair_structural).

Fallback: if Gemini fails or returns invalid JSON, the calling calculator
uses its own template-based output. Never crashes.
"""

import json
import logging
import os
import re
import urllib.request
import urllib.error
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class AICutListGenerator:
    """
    Generates detailed cut lists by sending structured job info to Gemini.

    Usage:
        generator = AICutListGenerator()
        cuts = generator.generate_cut_list("furniture_table", fields)
        if cuts:
            # Use AI-generated cut list
        else:
            # Fall back to template calculator
    """

    def generate_cut_list(self, job_type: str, fields: dict) -> Optional[List[Dict]]:
        """
        Generate an AI-assisted cut list from job fields.

        Args:
            job_type: The job type string (e.g. "furniture_table")
            fields: Answered fields from Stage 2

        Returns:
            List of cut item dicts matching MaterialItem schema, or None on failure.
            Each dict has: description, material_type, profile, length_inches,
            quantity, cut_type, notes.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.info("No GEMINI_API_KEY — skipping AI cut list")
            return None

        try:
            prompt = self._build_prompt(job_type, fields)
            response_text = self._call_gemini(prompt)
            cuts = self._parse_response(response_text)
            if cuts and len(cuts) > 0:
                return cuts
            logger.warning("AI cut list returned empty — falling back to template")
            return None
        except Exception as e:
            logger.warning("AI cut list generation failed: %s — falling back to template", e)
            return None

    def generate_build_instructions(self, job_type: str, fields: dict,
                                     cut_list: List[Dict]) -> Optional[List[Dict]]:
        """
        Generate fabrication sequence / build instructions.

        Args:
            job_type: The job type string
            fields: Answered fields from Stage 2
            cut_list: The material items list (from calculator output)

        Returns:
            List of step dicts [{step, title, description, tools, duration_minutes}],
            or None on failure.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.info("No GEMINI_API_KEY — skipping build instructions")
            return None

        try:
            prompt = self._build_instructions_prompt(job_type, fields, cut_list)
            response_text = self._call_gemini(prompt)
            steps = self._parse_instructions_response(response_text)
            if steps and len(steps) > 0:
                return steps
            logger.warning("AI build instructions returned empty — skipping")
            return None
        except Exception as e:
            logger.warning("AI build instructions failed: %s — skipping", e)
            return None

    def _build_prompt(self, job_type: str, fields: dict) -> str:
        """Build the Gemini prompt for cut list generation."""
        # Summarize fields for the prompt
        field_lines = []
        for key, val in fields.items():
            if val is not None and str(val).strip():
                field_lines.append("  - %s: %s" % (key, val))

        fields_text = "\n".join(field_lines) if field_lines else "  (no fields provided)"

        prompt = """You are an expert metal fabricator generating a cut list for a steel fabrication project.

JOB TYPE: %s

USER-PROVIDED FIELDS:
%s

TASK: Generate a detailed cut list — every piece of steel that needs to be cut for this project.

RULES:
1. Use standard steel profiles available at a metal supplier:
   - Square tube: sq_tube_1x1_14ga, sq_tube_1.5x1.5_11ga, sq_tube_2x2_11ga, sq_tube_2x2_14ga
   - Rectangular tube: rect_tube_2x3_11ga, rect_tube_2x4_11ga
   - Round tube: round_tube_1.5_14ga, round_tube_2_11ga
   - Flat bar: flat_bar_1x0.25, flat_bar_1.5x0.25, flat_bar_2x0.25
   - Angle: angle_1.5x1.5x0.125, angle_2x2x0.1875
   - Square bar: sq_bar_0.5, sq_bar_0.625, sq_bar_0.75
   - Channel: channel_4x5.4, channel_6x8.2
   - Pipe: pipe_3_sch40, pipe_4_sch40
   - Sheet/plate: sheet_11ga, sheet_14ga, sheet_16ga
2. Every piece must have a specific length in inches.
3. Use cut_type: "square", "miter_45", "cope", or "notch".
4. The material_type must be one of: square_tubing, round_tubing, flat_bar, angle_iron, channel, pipe, plate, mild_steel, stainless_304, aluminum_6061
5. Include a helpful "notes" field explaining what the piece is for.
6. Be practical — use standard sizes a fab shop would actually cut.
7. For tables/furniture: 4 legs (not 5), list frame rails individually (2 long rails + 2 short rails, not "perimeter").

Return ONLY valid JSON — an array of objects:
[
    {
        "description": "Table leg - 2x2 sq tube",
        "material_type": "square_tubing",
        "profile": "sq_tube_2x2_11ga",
        "length_inches": 30.0,
        "quantity": 4,
        "cut_type": "square",
        "notes": "4 legs at 30 inches each for 30-inch table height"
    }
]""" % (job_type, fields_text)

        return prompt

    def _build_instructions_prompt(self, job_type: str, fields: dict,
                                    cut_list: List[Dict]) -> str:
        """Build the Gemini prompt for fabrication sequence."""
        # Summarize fields
        field_lines = []
        for key, val in fields.items():
            if val is not None and str(val).strip():
                field_lines.append("  - %s: %s" % (key, val))
        fields_text = "\n".join(field_lines) if field_lines else "  (none)"

        # Summarize cut list
        cut_lines = []
        for item in cut_list[:20]:
            desc = item.get("description", "piece")
            qty = item.get("quantity", 1)
            length = item.get("length_inches", 0)
            cut_lines.append('  - %s (qty %d, %.0f")' % (desc, qty, length))
        cuts_text = "\n".join(cut_lines) if cut_lines else "  (no items)"

        prompt = """You are an expert metal fabricator creating step-by-step build instructions.

JOB TYPE: %s

FIELDS:
%s

CUT LIST:
%s

TASK: Generate a practical fabrication sequence — the steps a welder/fabricator would follow
to build this project from the cut list above.

RULES:
1. Steps should be in logical build order (layout, cut, fit, weld, grind, finish).
2. Each step should be specific and actionable.
3. Include tool recommendations (MIG welder, chop saw, angle grinder, etc.).
4. Estimate duration in minutes for each step.
5. 6-12 steps is typical. Don't over-complicate.
6. A journeyman fabricator should be able to follow these instructions.

Return ONLY valid JSON — an array of step objects:
[
    {
        "step": 1,
        "title": "Layout & Mark",
        "description": "Measure and mark all tube pieces per cut list. Mark miter angles on frame pieces.",
        "tools": ["tape measure", "soapstone", "speed square"],
        "duration_minutes": 20
    }
]""" % (job_type, fields_text, cuts_text)

        return prompt

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini API. Raises on failure."""
        api_key = os.getenv("GEMINI_API_KEY")
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "%s:generateContent?key=%s" % (model, api_key)
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read())
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text

    def _parse_response(self, response_text: str) -> Optional[List[Dict]]:
        """Parse Gemini response into cut list items."""
        try:
            # Try direct JSON parse
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON array from markdown code block
            match = re.search(r'\[[\s\S]*\]', response_text)
            if not match:
                logger.warning("Could not find JSON array in AI response")
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning("Failed to parse extracted JSON from AI response")
                return None

        if not isinstance(data, list):
            logger.warning("AI response is not a list")
            return None

        # Validate and normalize each item
        validated = []
        for item in data:
            if not isinstance(item, dict):
                continue
            cut = {
                "description": str(item.get("description", "Cut piece")),
                "material_type": str(item.get("material_type", "mild_steel")),
                "profile": str(item.get("profile", "sq_tube_1.5x1.5_11ga")),
                "length_inches": float(item.get("length_inches", 12.0)),
                "quantity": int(item.get("quantity", 1)),
                "cut_type": str(item.get("cut_type", "square")),
                "notes": str(item.get("notes", "")),
            }
            # Sanity checks
            if cut["length_inches"] <= 0:
                cut["length_inches"] = 12.0
            if cut["quantity"] <= 0:
                cut["quantity"] = 1
            if cut["cut_type"] not in ("square", "miter_45", "cope", "notch"):
                cut["cut_type"] = "square"
            validated.append(cut)

        return validated if validated else None

    def _parse_instructions_response(self, response_text: str) -> Optional[List[Dict]]:
        """Parse Gemini response into build instruction steps."""
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r'\[[\s\S]*\]', response_text)
            if not match:
                return None
            try:
                data = json.loads(match.group())
            except json.JSONDecodeError:
                return None

        if not isinstance(data, list):
            return None

        validated = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                continue
            step = {
                "step": int(item.get("step", i + 1)),
                "title": str(item.get("title", "Step %d" % (i + 1))),
                "description": str(item.get("description", "")),
                "tools": item.get("tools", []),
                "duration_minutes": int(item.get("duration_minutes", 15)),
            }
            if not isinstance(step["tools"], list):
                step["tools"] = [str(step["tools"])]
            validated.append(step)

        return validated if validated else None
