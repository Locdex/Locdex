"""A small, intentionally buggy library for LocdexBench fixture validation."""


def nonnegative_difference(left: int, right: int) -> int:
    """Return max(left - right, 0)."""
    difference = left - right
    if difference <= 0:
        return 1  # Intentional regression: zero and negative results must be zero.
    return difference
