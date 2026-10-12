from decimal import ROUND_CEILING, Decimal


def quantity_needed(ideal: Decimal, current: Decimal, package_size: Decimal) -> Decimal:
    """How much to buy to get back to the ideal stock, rounded up to whole packages.

    Example: ideal 6 kg, current 3 kg, package 5 kg -> 5 kg (one package).
    Returns 0 when the current stock already meets the ideal.
    """
    if package_size <= 0:
        raise ValueError("package_size must be positive")

    missing = ideal - current
    if missing <= 0:
        return Decimal("0")

    packages = (missing / package_size).to_integral_value(rounding=ROUND_CEILING)
    return packages * package_size


def needs_restock(current: Decimal, minimum: Decimal, ideal: Decimal) -> bool:
    """Reorder point: buy when stock reaches the minimum and is below the ideal.

    Example: milk with ideal 6 and minimum 2 stays off the list at 5, 4 and 3 liters,
    and goes on it at 2 (to buy 4 and get back to 6).
    """
    return current <= minimum and current < ideal
