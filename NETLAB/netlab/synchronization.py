from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from .contracts import ParticipantAck, RevisionStatus, Command, CommandStatus
from .revisions import RevisionStore, Revision, RevisionError
from .io import atomic_write_json, read_json, freshness, ensure_shared_directory

class Participant(Protocol):
    name:str
    def apply(self, revision:Revision, timeout_s:float)->ParticipantAck: ...

@dataclass
class FileParticipant:
    name:str; request_path:Path; ack_path:Path; required_hashes:tuple[str,...]=('config_hash',)
    poll_s:float=0.1
    def apply(self,revision:Revision,timeout_s:float)->ParticipantAck:
        atomic_write_json(self.request_path,{
            'revision_id':revision.revision_id,'command_id':revision.command_id,
            'hashes':revision.hashes,'candidate':revision.candidate,'timestamp':time.time()})
        deadline=time.monotonic()+timeout_s
        while time.monotonic()<deadline:
            ack=read_json(self.ack_path,{})
            if ack.get('revision_id')==revision.revision_id:
                return ParticipantAck(participant=self.name,revision_id=revision.revision_id,
                    accepted=bool(ack.get('accepted',False)),observed_hashes=ack.get('observed_hashes',{}),
                    message=ack.get('message',''),details=ack)
            time.sleep(self.poll_s)
        return ParticipantAck(participant=self.name,revision_id=revision.revision_id,accepted=False,
                              message=f'{self.name} acknowledgement timeout after {timeout_s:.1f}s')

@dataclass
class ImmediateParticipant:
    name:str; accept:bool=True
    def apply(self,revision:Revision,timeout_s:float)->ParticipantAck:
        return ParticipantAck(self.name,revision.revision_id,self.accept,dict(revision.hashes),
                              message='embedded acceptance participant')

class SynchronizationCoordinator:
    def __init__(self,store:RevisionStore,participants:list[Participant],state_root:str|Path):
        self.store=store; self.participants=participants; self.state_root=ensure_shared_directory(state_root)
        self.status_path=self.state_root/'synchronization_status.json'
    def _status(self,revision:Revision,stage:str,extra:dict[str,Any]|None=None):
        payload={'revision_id':revision.revision_id,'stage':stage,'status':revision.status.value,
                 'hashes':revision.hashes,'acknowledgements':revision.acknowledgements,
                 'updated_at':time.time()}
        if extra: payload.update(extra)
        atomic_write_json(self.status_path,payload)
    def apply(self,candidate:dict[str,Any],*,command:Command|None=None,timeout_s:float=30.0)->tuple[Revision,Command]:
        command=command or Command('apply_configuration',payload={'candidate':candidate})
        command.status=CommandStatus.VALIDATING
        revision=self.store.create(candidate,command_id=command.command_id,
                                   idempotency_key=command.idempotency_key,initiator=command.initiator)
        revision.status=RevisionStatus.VALIDATED; self.store.save(revision)
        command.requested_revision=revision.revision_id; command.status=CommandStatus.DISPATCHING
        self._status(revision,'VALIDATED')
        mapping={'ros':RevisionStatus.PENDING_ROS,'sionna':RevisionStatus.PENDING_SIONNA,'isaac':RevisionStatus.PENDING_ISAAC}
        applied={'ros':RevisionStatus.APPLIED_TO_ROS,'sionna':RevisionStatus.APPLIED_TO_SIONNA,'isaac':RevisionStatus.APPLIED_TO_ISAAC}
        for participant in self.participants:
            revision.status=mapping.get(participant.name,RevisionStatus.PENDING_RUNTIME_APPLY); self.store.save(revision)
            command.status=CommandStatus.WAITING_FOR_ACK; self._status(revision,f'WAITING_FOR_{participant.name.upper()}')
            ack=participant.apply(revision,timeout_s)
            self.store.acknowledge(revision,ack); command.acknowledgements[participant.name]=revision.acknowledgements[participant.name]
            if not ack.accepted:
                revision.status=RevisionStatus.DEGRADED; revision.error={'code':f'{participant.name.upper()}_ACK_FAILED','message':ack.message}
                self.store.save(revision); command.status=CommandStatus.PARTIALLY_APPLIED
                command.error=revision.error; self._status(revision,'DEGRADED',{'failed_participant':participant.name})
                return revision,command
            revision.status=applied.get(participant.name,RevisionStatus.PENDING_RUNTIME_APPLY); self.store.save(revision)
        revision.status=RevisionStatus.IN_SYNC; self.store.save(revision)
        try: self.store.commit(revision,tuple(p.name for p in self.participants))
        except RevisionError as exc:
            revision.status=RevisionStatus.DRIFT_DETECTED; revision.error={'code':'REVISION_DRIFT','message':str(exc)}
            self.store.save(revision); command.status=CommandStatus.FAILED; command.error=revision.error
            self._status(revision,'DRIFT_DETECTED'); return revision,command
        command.status=CommandStatus.COMPLETED; command.resulting_revision=revision.revision_id
        self._status(revision,'COMMITTED'); return revision,command
    def inspect(self)->dict[str,Any]:
        desired=self.store.desired(); current=self.store.current(); status=read_json(self.status_path,{})
        return {'desired_revision':desired.revision_id if desired else '',
                'committed_revision':current.revision_id if current else '',
                'in_sync':bool(desired and current and desired.revision_id==current.revision_id),
                'status':status}

# ---------------------------------------------------------------------------
# Runtime-facing transactional synchronizer used by the authoritative
# Orchestrator and Mission Control application.
# ---------------------------------------------------------------------------
import json
import urllib.error
import urllib.request
from .models import ParticipantState
from .revisions import RevisionManager


class RuntimeSynchronizer:
    """Apply one durable revision to ROS 2, Sionna, and Isaac in order."""

    def __init__(self, root: str | Path, compose: Any = None):
        self.root = Path(root).resolve()
        self.compose = compose
        self.manager = RevisionManager(self.root)
        self.shared = ensure_shared_directory(self.root / "Docker/workspace/shared")
        self.results = ensure_shared_directory(self.root / "Docker/workspace/results")
        self.shared_revision_dir = ensure_shared_directory(self.shared / "revisions")

    @staticmethod
    def _payload(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision_id": record["revision_id"],
            "revision": record["revision_id"],
            "parent_revision_id": record.get("parent_revision_id", ""),
            "command_id": record.get("command_id", ""),
            "idempotency_key": record.get("idempotency_key", ""),
            "hashes": record.get("hashes", {}),
            "candidate": record.get("config") or record.get("candidate") or {},
            "configuration": record.get("config") or record.get("candidate") or {},
            "reason": record.get("reason", "runtime_apply"),
            "timestamp": time.time(),
        }

    @staticmethod
    def _wait_ack(paths: list[Path], revision_id: str, timeout_s: float) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.05, timeout_s)
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            for path in paths:
                value = read_json(path, {}) or {}
                if value:
                    latest = value
                observed = str(value.get("revision_id") or value.get("revision") or "")
                if observed == revision_id:
                    return value
            time.sleep(0.1)
        return latest

    def _mark_from_ack(self, record: dict[str, Any], participant: str, ack: dict[str, Any]) -> dict[str, Any]:
        accepted = bool(ack.get("accepted", ack.get("ok", ack.get("ready", False))))
        observed_hashes = ack.get("observed_hashes") or ack.get("applied_hashes") or ack.get("hashes") or {}
        return self.manager.mark_participant(
            record["revision_id"],
            participant,
            state=ParticipantState.ACKNOWLEDGED if accepted else ParticipantState.FAILED,
            observed_revision=str(ack.get("revision_id") or ack.get("revision") or ""),
            observed_hashes=dict(observed_hashes),
            message=str(ack.get("message") or ack.get("error") or ""),
            details=ack,
        )

    def _apply_ros(self, record: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        payload = self._payload(record)
        atomic_write_json(self.shared / "revision_ros_request.json", payload)
        ack = self._wait_ack(
            [self.results / "revision_ros_ack.json", self.results / "snaas_ros_revision_ack.json"],
            record["revision_id"],
            timeout_s,
        )
        if ack:
            self._mark_from_ack(record, "ros", ack)
        return ack

    def _apply_sionna(self, record: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        payload = self._payload(record)
        request = urllib.request.Request(
            "http://127.0.0.1:8090/config/apply",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(0.1, timeout_s)) as response:
                ack = json.load(response)
        except Exception as exc:
            ack = {"ok": False, "accepted": False, "message": str(exc), "revision_id": record["revision_id"]}
        if ack.get("ok") or ack.get("accepted"):
            self._mark_from_ack(record, "sionna", ack)
        return ack

    def _apply_isaac(self, record: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        payload = self._payload(record)
        candidate_path = self.shared_revision_dir / f"{record['revision_id']}.json"
        candidate = dict(payload.get("candidate") or {})
        candidate["_netlab_revision"] = {
            "revision_id": record["revision_id"],
            "parent_revision_id": record.get("parent_revision_id", ""),
            "command_id": record.get("command_id", ""),
            **dict(record.get("hashes") or {}),
        }
        atomic_write_json(candidate_path, candidate)
        payload["config_path"] = str(candidate_path)
        atomic_write_json(self.shared / "revision_isaac_request.json", payload)
        # Preserve the compatibility signal consumed by the persistent scene controller.
        atomic_write_json(self.results / "snaas_isaac_sync_signal.json", payload)
        ack = self._wait_ack(
            [self.results / "snaas_isaac_sync_ack.json"],
            record["revision_id"],
            timeout_s,
        )
        if ack:
            self._mark_from_ack(record, "isaac", ack)
        return ack

    def apply(
        self,
        record: dict[str, Any],
        *,
        ros_timeout_s: float = 30.0,
        sionna_timeout_s: float = 15.0,
        isaac_timeout_s: float = 60.0,
        offline_is_pending: bool = True,
    ) -> dict[str, Any]:
        revision_id = str(record["revision_id"])
        results: dict[str, Any] = {}
        pending: list[str] = []
        for participant, callback, timeout in (
            ("ros", self._apply_ros, ros_timeout_s),
            ("sionna", self._apply_sionna, sionna_timeout_s),
            ("isaac", self._apply_isaac, isaac_timeout_s),
        ):
            ack = callback(record, timeout)
            accepted = bool(ack and ack.get("revision_id", ack.get("revision")) == revision_id and ack.get("accepted", ack.get("ok", ack.get("ready", False))))
            results[participant] = {"accepted": accepted, "acknowledgement": ack}
            if not accepted:
                pending.append(participant)
                if not offline_is_pending:
                    break
        current = self.manager.read(revision_id)
        committable = self.manager.all_required_acknowledged(current)
        transaction = {
            "revision_id": revision_id,
            "committable": committable,
            "pending": pending,
            "participants": results,
            "synchronization": self.manager.status(revision_id),
            "error": None if committable else {
                "code": "RUNTIME_ACKNOWLEDGEMENTS_PENDING" if offline_is_pending else "RUNTIME_ACKNOWLEDGEMENT_FAILED",
                "message": "Required runtime participants have not acknowledged the same revision and hashes.",
                "pending_participants": pending,
            },
        }
        atomic_write_json(self.results / "netlab_runtime_transaction.json", transaction)
        return transaction

    def reconcile(self, revision_id: str = "", *, isaac_timeout_s: float = 60.0) -> dict[str, Any]:
        if not revision_id:
            desired = self.manager.desired()
            revision_id = str(desired.get("revision_id", ""))
        if not revision_id:
            return {"revision_id": "", "committable": False, "pending": [], "error": {"code": "NO_DESIRED_REVISION", "message": "No desired revision exists."}}
        return self.apply(
            self.manager.read(revision_id),
            ros_timeout_s=30.0,
            sionna_timeout_s=15.0,
            isaac_timeout_s=isaac_timeout_s,
            offline_is_pending=True,
        )
