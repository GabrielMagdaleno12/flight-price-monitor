from typing import Optional


def should_alert(
    current_price: float,
    price_ceiling: Optional[float],
    lowest_price_seen: Optional[float],
    drop_pct_threshold: Optional[float],
) -> bool:
    if price_ceiling is not None and current_price <= price_ceiling:
        return True

    if drop_pct_threshold is not None and lowest_price_seen is not None:
        threshold_price = lowest_price_seen * (1 - drop_pct_threshold / 100)
        if current_price <= threshold_price:
            return True

    return False
