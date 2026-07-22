"""Authoritative packet/branch-stream state machine.

This module is simulator independent. The ROS 2 runtime mirrors these semantics:
a packet cursor changes only after a feasible-hop decision. Isaac visualization
must consume resulting packet events rather than animate independently.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .models import FeasibilityDecision, GateReason, PacketState, PacketStatus, RuntimeEvent

GateEvaluator = Callable[[str, str], FeasibilityDecision]


@dataclass
class BranchStream:
    branch_id: str
    route: List[str]
    source: str
    destination: str
    flow_id: str
    packet_size_bytes: int = 512
    priority: int = 0
    current_packet: Optional[PacketState] = None
    completed_packets: int = 0
    dropped_packets: int = 0
    paused: bool = False
    outage_reason: Optional[str] = None
    last_decision: Optional[Dict[str, Any]] = None
    last_event_at: float = 0.0

    def new_packet(self, sequence_number: int) -> PacketState:
        packet = PacketState(
            packet_id=str(uuid.uuid4()),
            flow_id=self.flow_id,
            branch_id=self.branch_id,
            sequence_number=sequence_number,
            source=self.source,
            destination=self.destination,
            route=list(self.route),
            current_hop_index=0,
            current_node=self.route[0],
            next_node=self.route[1] if len(self.route) > 1 else "",
            status=PacketStatus.QUEUED,
            queued_at=time.time(),
            bytes=self.packet_size_bytes,
            priority=self.priority,
        )
        self.current_packet = packet
        self.paused = False
        self.outage_reason = None
        return packet

    def as_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "flow_id": self.flow_id,
            "route": self.route,
            "source": self.source,
            "destination": self.destination,
            "current_packet": self.current_packet.as_dict() if self.current_packet else None,
            "completed_packets": self.completed_packets,
            "dropped_packets": self.dropped_packets,
            "paused": self.paused,
            "outage_reason": self.outage_reason,
            "last_decision": self.last_decision,
            "last_event_at": self.last_event_at,
        }


@dataclass
class PacketRuntime:
    mode: str
    streams: Dict[str, BranchStream]
    experiment_id: str = ""
    run_id: str = ""
    sequence: int = 0
    event_sequence: int = 0
    events: List[RuntimeEvent] = field(default_factory=list)

    @classmethod
    def from_branches(
        cls,
        branches: Sequence[Sequence[int]],
        *,
        mode: str,
        source: str = "station",
        experiment_id: str = "",
        run_id: str = "",
        packet_size_bytes: int = 512,
    ) -> "PacketRuntime":
        streams: Dict[str, BranchStream] = {}
        for branch_index, branch in enumerate(branches):
            route = [source] + [f"drone_{int(idx)}" for idx in branch]
            if len(route) < 2:
                continue
            branch_id = f"branch_{branch_index}"
            streams[branch_id] = BranchStream(
                branch_id=branch_id,
                route=route,
                source=route[0],
                destination=route[-1],
                flow_id=f"flow_{branch_index}",
                packet_size_bytes=packet_size_bytes,
            )
        return cls(mode=mode, streams=streams, experiment_id=experiment_id, run_id=run_id)

    def _event(self, event_type: str, payload: Mapping[str, Any], *, severity: str = "INFO", entity: str = "") -> RuntimeEvent:
        self.event_sequence += 1
        event = RuntimeEvent(
            event_type=event_type,
            source_component="packet_runtime",
            payload=dict(payload),
            severity=severity,
            experiment_id=self.experiment_id,
            run_id=self.run_id,
            affected_entity=entity,
            sequence=self.event_sequence,
        )
        self.events.append(event)
        return event

    def ensure_packets(self) -> None:
        for stream in self.streams.values():
            if stream.current_packet is None:
                self.sequence += 1
                packet = stream.new_packet(self.sequence)
                self._event("PACKET_CREATED", {"packet": packet.as_dict()}, entity=stream.branch_id)

    def step_stream(self, stream: BranchStream, gate: GateEvaluator) -> RuntimeEvent:
        if stream.current_packet is None:
            self.sequence += 1
            stream.new_packet(self.sequence)
        packet = stream.current_packet
        assert packet is not None
        now = time.time()

        if packet.status == PacketStatus.DELIVERED:
            # Delivery was accounted for when the delivery event was emitted.
            # Create the next packet without incrementing the completed counter twice.
            self.sequence += 1
            packet = stream.new_packet(self.sequence)
            self._event("PACKET_CREATED", {"packet": packet.as_dict()}, entity=stream.branch_id)

        if packet.current_hop_index >= len(packet.route) - 1:
            packet.status = PacketStatus.DELIVERED
            packet.received_at = now
            stream.completed_packets += 1
            stream.last_event_at = now
            return self._event("PACKET_DELIVERED", {"packet": packet.as_dict()}, entity=stream.branch_id)

        src = packet.route[packet.current_hop_index]
        dst = packet.route[packet.current_hop_index + 1]
        packet.current_node = src
        packet.next_node = dst
        packet.status = PacketStatus.WAITING_FOR_LINK
        decision = gate(src, dst)
        stream.last_decision = decision.as_dict()
        stream.last_event_at = now

        if not decision.feasible:
            packet.status = PacketStatus.PAUSED_OUTAGE
            packet.outage_reason = decision.reason.value
            stream.paused = True
            stream.outage_reason = decision.reason.value
            return self._event(
                "PACKET_PAUSED_OUTAGE",
                {
                    "packet": packet.as_dict(),
                    "src": src,
                    "dst": dst,
                    "gate": decision.as_dict(),
                    "protocol_action": "cursor_not_advanced",
                },
                severity="WARNING",
                entity=stream.branch_id,
            )

        packet.status = PacketStatus.TRANSMITTING
        packet.transmitted_at = now
        packet.last_link_metric_id = None
        packet.current_hop_index += 1
        packet.current_node = dst
        packet.next_node = packet.route[packet.current_hop_index + 1] if packet.current_hop_index + 1 < len(packet.route) else ""
        packet.outage_reason = None
        stream.paused = False
        stream.outage_reason = None

        if packet.current_hop_index >= len(packet.route) - 1:
            packet.status = PacketStatus.DELIVERED
            packet.received_at = now
            stream.completed_packets += 1
            return self._event(
                "PACKET_DELIVERED",
                {"packet": packet.as_dict(), "src": src, "dst": dst, "gate": decision.as_dict()},
                entity=stream.branch_id,
            )

        packet.status = PacketStatus.ADVANCED
        return self._event(
            "PACKET_ADVANCED",
            {"packet": packet.as_dict(), "src": src, "dst": dst, "gate": decision.as_dict()},
            entity=stream.branch_id,
        )

    def step(self, gate: GateEvaluator) -> List[RuntimeEvent]:
        self.ensure_packets()
        emitted: List[RuntimeEvent] = []
        if self.mode == "chain":
            stream = next(iter(self.streams.values()), None)
            if stream:
                emitted.append(self.step_stream(stream, gate))
        else:
            for stream in self.streams.values():
                emitted.append(self.step_stream(stream, gate))
        return emitted

    def clear_outage(self, branch_id: Optional[str] = None) -> None:
        targets = [self.streams[branch_id]] if branch_id and branch_id in self.streams else list(self.streams.values())
        for stream in targets:
            stream.paused = False
            stream.outage_reason = None
            if stream.current_packet and stream.current_packet.status == PacketStatus.PAUSED_OUTAGE:
                stream.current_packet.status = PacketStatus.RETRYING
                stream.current_packet.retries += 1
                stream.current_packet.outage_reason = None
            self._event("PACKET_RETRY_ENABLED", {"branch_id": stream.branch_id}, entity=stream.branch_id)

    def replace_route(self, branch_id: str, route: Sequence[str]) -> None:
        if branch_id not in self.streams:
            raise KeyError(branch_id)
        if len(route) < 2:
            raise ValueError("route must contain source and destination")
        stream = self.streams[branch_id]
        stream.route = list(route)
        stream.source = route[0]
        stream.destination = route[-1]
        self.sequence += 1
        stream.new_packet(self.sequence)
        self._event("ROUTE_RECOMPUTED", {"branch_id": branch_id, "route": list(route)}, entity=branch_id)

    def summary(self) -> Dict[str, Any]:
        packets = [s.current_packet for s in self.streams.values() if s.current_packet]
        paused = [s.branch_id for s in self.streams.values() if s.paused]
        delivered = sum(s.completed_packets for s in self.streams.values())
        return {
            "mode": self.mode,
            "stream_count": len(self.streams),
            "streams": [s.as_dict() for s in self.streams.values()],
            "packet_advancing": any(p and p.status in {PacketStatus.ADVANCED, PacketStatus.TRANSMITTING, PacketStatus.DELIVERED} for p in packets),
            "paused_branches": paused,
            "all_paused": bool(self.streams) and len(paused) == len(self.streams),
            "delivered_packets": delivered,
            "event_sequence": self.event_sequence,
        }


def constant_decision(feasible: bool, reason: GateReason = GateReason.FEASIBLE) -> FeasibilityDecision:
    return FeasibilityDecision(feasible=feasible, reason=reason, predicates=[])
