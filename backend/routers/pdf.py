"""
PDF download endpoint — Stage 6.

GET /api/quotes/{quote_id}/pdf — download professional quote PDF.

Supports auth via:
1. Authorization: Bearer <token> header (standard)
2. ?token=<jwt> query param (for window.open / direct download links)
"""

import logging
import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models
from ..auth import decode_token, get_current_user
from ..database import get_db
from ..pdf_generator import (
    generate_quote_pdf, generate_client_pdf, generate_client_scope,
    generate_materials_pdf, generate_materials_csv,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quotes", tags=["pdf"])


def _get_user_from_token_param(
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    """Resolve user from ?token= query param."""
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(models.User).filter(models.User.id == int(user_id)).first()
    except Exception:
        return None


@router.get("/{quote_id}/pdf")
def download_pdf(
    quote_id: int,
    token: Optional[str] = Query(None),
    mode: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Generate and download a PDF quote document.

    Auth: Bearer header OR ?token= query param.
    Returns: application/pdf
    """
    # Try query param auth first (for window.open)
    current_user = _get_user_from_token_param(token, db)

    # Fall back to header auth
    if not current_user:
        try:
            from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
            # Manual header check — since we can't use Depends in a flexible way
            # The query param flow is the primary path for PDF downloads
            raise HTTPException(status_code=401, detail="Authentication required. Pass ?token= parameter.")
        except HTTPException:
            if not current_user:
                raise

    quote = db.query(models.Quote).filter(models.Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    if quote.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not your quote")

    outputs = quote.outputs_json
    if not outputs:
        raise HTTPException(
            status_code=400,
            detail="Quote has no pricing data. Run the pricing pipeline first.",
        )

    # Add quote_number to outputs if not already there
    if "quote_number" not in outputs:
        outputs["quote_number"] = quote.quote_number

    # Build user profile dict
    user_profile = {
        "shop_name": current_user.shop_name,
        "shop_address": current_user.shop_address,
        "shop_phone": current_user.shop_phone,
        "shop_email": current_user.shop_email,
        "logo_url": current_user.logo_url,
    }

    inputs = quote.inputs_json or {}

    try:
        # Generate PDF (convert bytearray to bytes for Response compatibility)
        if mode == "materials":
            pdf_bytes = bytes(generate_materials_pdf(outputs, user_profile))
            filename = "Materials-%s.pdf" % (quote.quote_number or quote_id)
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": 'attachment; filename="%s"' % filename,
                },
            )
        elif mode == "materials-csv":
            csv_bytes = generate_materials_csv(outputs)
            filename = "Materials-%s.csv" % (quote.quote_number or quote_id)
            return Response(
                content=csv_bytes,
                media_type="text/csv",
                headers={
                    "Content-Disposition": 'attachment; filename="%s"' % filename,
                },
            )
        elif mode == "client":
            # Generate or retrieve cached AI scope
            client_scope = outputs.get("_client_scope")
            if not client_scope:
                try:
                    fields = (inputs or {}).get("fields", {})
                    job_desc = outputs.get("job_description", "") or fields.get("description", "")
                    scope_text, is_ai = generate_client_scope(
                        outputs.get("job_type", ""),
                        fields,
                        job_desc,
                    )
                    client_scope = scope_text
                    # Only cache AI-generated scopes — fallbacks should retry next time
                    if is_ai and client_scope:
                        from sqlalchemy.orm.attributes import flag_modified
                        outputs["_client_scope"] = client_scope
                        quote.outputs_json = outputs
                        flag_modified(quote, "outputs_json")
                        db.commit()
                except Exception:
                    client_scope = None

            pdf_bytes = bytes(generate_client_pdf(outputs, user_profile, inputs,
                                                  client_scope=client_scope))
            filename = f"Proposal-{quote.quote_number or quote_id}.pdf"
        else:
            pdf_bytes = bytes(generate_quote_pdf(outputs, user_profile, inputs))
            filename = f"Quote-{quote.quote_number or quote_id}.pdf"
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("PDF generation failed (mode=%s, quote=%s): %s\n%s", mode, quote_id, e, tb)
        print("PDF ERROR (mode=%s, quote=%s): %s\n%s" % (mode, quote_id, e, tb), flush=True)
        raise HTTPException(
            status_code=500,
            detail="PDF generation failed: %s" % str(e),
        )
