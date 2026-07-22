import math
import unittest

from netlab.link import free_space_path_loss_db


class ScientificReferenceTests(unittest.TestCase):
    def test_fspl_matches_equivalent_km_mhz_expression(self):
        distance_m = 100.0
        frequency_hz = 3.5e9
        direct = free_space_path_loss_db(distance_m, frequency_hz)
        equivalent = 32.447783 + 20 * math.log10(distance_m / 1000.0) + 20 * math.log10(frequency_hz / 1e6)
        self.assertAlmostEqual(direct, equivalent, places=2)


if __name__ == "__main__":
    unittest.main()
