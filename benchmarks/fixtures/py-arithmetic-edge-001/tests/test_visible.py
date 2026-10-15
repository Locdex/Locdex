"""Public regression tests provided to the coding agent."""
import unittest

from core import nonnegative_difference


class DifferenceTests(unittest.TestCase):
    def test_positive_difference(self):
        self.assertEqual(nonnegative_difference(8, 3), 5)

    def test_zero_difference(self):
        self.assertEqual(nonnegative_difference(4, 4), 0)


if __name__ == "__main__":
    unittest.main()
