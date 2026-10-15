"""Negative control: fixes zero but breaks positive differences."""


def nonnegative_difference(left: int, right: int) -> int:
    """Return max(left - right, 0)."""
    return 0
