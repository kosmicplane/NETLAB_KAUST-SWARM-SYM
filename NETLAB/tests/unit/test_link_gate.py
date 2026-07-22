import time
import unittest

from netlab.link import LinkRequest, compute_analytical_link, evaluate_feasibility, free_space_path_loss_db, thermal_noise_dbm
from netlab.models import GateReason


class LinkGateTests(unittest.TestCase):
    def request(self, distance=30.0, **kwargs):
        data = dict(src="station", dst="drone_1", tx_position=[0, 0, 1.5], rx_position=[distance, 0, 30], frequency_hz=3.5e9, bandwidth_hz=20e6, tx_power_dbm=23.0, tx_gain_dbi=8.0, rx_gain_dbi=2.5)
        data.update(kwargs)
        return LinkRequest(**data)

    def decide(self, metrics, **kwargs):
        params = dict(source_active=True, destination_active=True, source_failed=False, destination_failed=False, operational_range_m=90.0, hard_outage_distance_m=220.0, min_snr_db=3.0, min_sinr_db=3.0, min_capacity_mbps=1.0, metric_ttl_s=2.0)
        params.update(kwargs)
        return evaluate_feasibility(metrics, **params)

    def test_analytical_reference_equations(self):
        self.assertAlmostEqual(thermal_noise_dbm(20e6, 7.0), -93.9897, places=3)
        self.assertAlmostEqual(free_space_path_loss_db(1.0, 3.5e9), 43.3291, places=3)

    def test_feasible_hop(self):
        metrics = compute_analytical_link(self.request())
        decision = self.decide(metrics)
        self.assertTrue(decision.feasible)
        self.assertEqual(decision.reason, GateReason.FEASIBLE)
        self.assertTrue(all(p.passed for p in decision.predicates))

    def test_gate_reasons_are_specific_and_ordered(self):
        metrics = compute_analytical_link(self.request())
        self.assertEqual(self.decide(metrics, source_failed=True).reason, GateReason.SOURCE_FAILED)
        far = compute_analytical_link(self.request(distance=500.0))
        self.assertEqual(self.decide(far).reason, GateReason.HARD_OUTAGE_DISTANCE)
        medium = compute_analytical_link(self.request(distance=100.0))
        self.assertEqual(self.decide(medium).reason, GateReason.OUT_OF_RANGE)
        self.assertEqual(self.decide(metrics, min_snr_db=200.0).reason, GateReason.SNR_BELOW_THRESHOLD)
        self.assertEqual(self.decide(metrics, min_capacity_mbps=1e9).reason, GateReason.CAPACITY_BELOW_THRESHOLD)

    def test_stale_metric_is_rejected(self):
        metrics = compute_analytical_link(self.request())
        metrics.timestamp_wall_s = time.time() - 30
        self.assertEqual(self.decide(metrics).reason, GateReason.STALE_LINK_METRIC)

    def test_stochastic_seed_is_process_stable(self):
        request = self.request(model="stochastic_shadowing", shadowing_sigma_db=4.0, seed=42)
        first = compute_analytical_link(request)
        second = compute_analytical_link(request)
        self.assertEqual(first.components_db["shadowing_db"], second.components_db["shadowing_db"])


if __name__ == "__main__":
    unittest.main()
