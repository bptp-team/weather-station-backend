PASCAL_PER_ATM = 101325.0


def pascal_to_atm(pascal: float) -> float:
    """Convert absolute pressure from pascal to standard atmospheres."""
    return pascal / PASCAL_PER_ATM
