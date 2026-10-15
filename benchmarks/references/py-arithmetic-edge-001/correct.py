"""Reference implementation used only by the fixture validator."""


def nonnegative_difference(left: int, right: int) -> int:
    """Return max(left - right, 0)."""
    return max(left - right, 0)
