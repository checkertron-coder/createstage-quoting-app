"""
Historical Validator — compares AI labor estimates against historical actuals.

Sets flagged=True if variance > 25%.

For now, this is a stub — the historical_actuals table is empty.
When Burton records actual hours after completing jobs, this becomes
the accuracy feedback loop that makes the AI estimates better over time.
"""

from datetime import datetime


class HistoricalValidator:
    """
    Compares AI labor estimates against historical actuals.
    Sets flagged=True if variance > 25%.
    """

    VARIANCE_THRESHOLD = 0.25  # 25%

    def validate(self, estimate: dict, job_type: str, db_session=None) -> dict:
        """
        Checks estimate against historical actuals for this job type.
        Returns the estimate dict with flagged/flag_reason set.

        If no historical data exists: flagged=False, flag_reason=None
        If data exists and variance > 25%: flagged=True, flag_reason explains
        """
        if db_session is None:
            # No DB session — can't check history
            estimate["flagged"] = False
            estimate["flag_reason"] = None
            return estimate

        try:
            from . import models

            # Query historical actuals for this job type
            actuals = db_session.query(models.HistoricalActual).join(
                models.Quote,
                models.HistoricalActual.quote_id == models.Quote.id,
            ).filter(
                models.Quote.job_type == job_type,
            ).all()

            if not actuals:
                # No historical data — nothing to compare against
                estimate["flagged"] = False
                estimate["flag_reason"] = None
                return estimate

            # Compute average historical total hours
            historical_totals = []
            for actual in actuals:
                hours_by_process = actual.actual_hours_by_process or {}
                total = sum(hours_by_process.values())
                if total > 0:
                    historical_totals.append(total)

            if not historical_totals:
                estimate["flagged"] = False
                estimate["flag_reason"] = None
                return estimate

            avg_historical = sum(historical_totals) / len(historical_totals)
            estimated_total = estimate.get("total_hours", 0)

            if avg_historical > 0:
                variance = abs(estimated_total - avg_historical) / avg_historical
                if variance > self.VARIANCE_THRESHOLD:
                    estimate["flagged"] = True
                    pct = round(variance * 100, 1)
                    direction = "higher" if estimated_total > avg_historical else "lower"
                    estimate["flag_reason"] = (
                        f"Estimate is {pct}% {direction} than historical average "
                        f"({estimated_total:.1f} hrs vs. {avg_historical:.1f} hrs avg "
                        f"from {len(historical_totals)} past jobs)"
                    )
                else:
                    estimate["flagged"] = False
                    estimate["flag_reason"] = None
            else:
                estimate["flagged"] = False
                estimate["flag_reason"] = None

        except Exception:
            # Any DB error — don't block the estimate
            estimate["flagged"] = False
            estimate["flag_reason"] = None

        return estimate

    def record_actual(self, quote_id: int, actual_hours_by_process: dict,
                      actual_material_cost: float, notes: str, db_session=None) -> None:
        """
        Records actual hours after a job is completed.
        This is how the system learns over time.
        Called from a future "record actuals" UI/endpoint.
        """
        if db_session is None:
            return

        from . import models

        # Compute variance vs. estimated if quote has outputs
        variance_pct = None
        quote = db_session.query(models.Quote).filter(
            models.Quote.id == quote_id,
        ).first()
        if quote and quote.outputs_json:
            estimated_hours = quote.outputs_json.get("labor", {}).get("total_hours")
            if estimated_hours and estimated_hours > 0:
                actual_total = sum(actual_hours_by_process.values())
                variance_pct = round(
                    (actual_total - estimated_hours) / estimated_hours, 4
                )

        actual = models.HistoricalActual(
            quote_id=quote_id,
            actual_hours_by_process=actual_hours_by_process,
            actual_material_cost=actual_material_cost,
            notes=notes,
            variance_pct=variance_pct,
            recorded_at=datetime.utcnow(),
        )
        db_session.add(actual)
        db_session.commit()
