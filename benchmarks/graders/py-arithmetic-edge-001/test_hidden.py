"""Held-out grader; this file must not be mounted in an agent workspace."""
import unittest

from core import nonnegative_difference


class HiddenDifferenceTests(unittest.TestCase):
    def test_negative_difference_is_zero(self):
        self.assertEqual(nonnegative_difference(2, 8), 0)

    def test_exact_zero_is_zero(self):
        self.assertEqual(nonnegative_difference(0, 0), 0)

    def test_positive_result_preserves_value(self):
        self.assertEqual(nonnegative_difference(13, 5), 8)


if __name__ == "__main__":
    unittest.main()
