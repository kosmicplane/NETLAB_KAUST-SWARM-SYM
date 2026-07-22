import unittest

from netlab.models import GateReason, PacketStatus
from netlab.packet import PacketRuntime, constant_decision


class PacketRuntimeTests(unittest.TestCase):
    def test_feasible_chain_advances_and_counts_once(self):
        runtime = PacketRuntime.from_branches([[1, 2]], mode="chain")
        runtime.step(lambda _src, _dst: constant_decision(True))
        packet = runtime.streams["branch_0"].current_packet
        self.assertEqual(packet.current_hop_index, 1)
        self.assertEqual(packet.status, PacketStatus.ADVANCED)
        runtime.step(lambda _src, _dst: constant_decision(True))
        self.assertEqual(runtime.streams["branch_0"].completed_packets, 1)
        runtime.step(lambda _src, _dst: constant_decision(True))
        self.assertEqual(runtime.streams["branch_0"].completed_packets, 1, "delivery must not be double counted")

    def test_infeasible_gate_never_advances_cursor(self):
        runtime = PacketRuntime.from_branches([[1, 2]], mode="chain")
        runtime.step(lambda _src, _dst: constant_decision(False, GateReason.OUT_OF_RANGE))
        packet = runtime.streams["branch_0"].current_packet
        self.assertEqual(packet.current_hop_index, 0)
        self.assertEqual(packet.status, PacketStatus.PAUSED_OUTAGE)
        self.assertEqual(packet.outage_reason, GateReason.OUT_OF_RANGE.value)

    def test_parallel_streams_are_independent(self):
        runtime = PacketRuntime.from_branches([[1, 3], [2, 4]], mode="parallel")
        def gate(src, _dst):
            return constant_decision(src != "station" or _dst != "drone_1", GateReason.OUT_OF_RANGE)
        runtime.step(gate)
        self.assertTrue(runtime.streams["branch_0"].paused)
        self.assertFalse(runtime.streams["branch_1"].paused)
        self.assertEqual(runtime.streams["branch_0"].current_packet.current_hop_index, 0)
        self.assertEqual(runtime.streams["branch_1"].current_packet.current_hop_index, 1)


if __name__ == "__main__":
    unittest.main()
