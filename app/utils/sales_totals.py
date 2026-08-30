"""Shared sale amount calculations used by dashboards and receipts."""


def sale_total_for_display(sale):
    """Return stored sale total, falling back to calculated item totals for legacy rows."""
    stored_total = max(0.0, float(getattr(sale, 'total', 0) or 0))
    if stored_total > 0:
        return stored_total
    try:
        return max(0.0, sum(
            (float(item.price or 0) * float(item.quantity or 0))
            - float(item.discount or 0)
            + float(item.tax or 0)
            for item in (getattr(sale, 'items', None) or [])
        ))
    except Exception:
        return 0.0
