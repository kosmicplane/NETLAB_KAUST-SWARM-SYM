from __future__ import annotations
import time, uuid
from pathlib import Path
from typing import Any
from .contracts import Revision, RevisionStatus, ParticipantAck
from .hashing import component_hashes
from .io import atomic_write_json, read_json, ensure_shared_directory

class RevisionError(RuntimeError): pass

class RevisionStore:
    def __init__(self, root:str|Path):
        self.root=ensure_shared_directory(root); self.revisions=ensure_shared_directory(self.root/'revisions')
        self.current_path=self.root/'revision_current.json'; self.desired_path=self.root/'revision_desired.json'
    def _path(self,rid:str)->Path: return self.revisions/f'{rid}.json'
    def create(self,candidate:dict[str,Any],*,command_id:str='',idempotency_key:str='',initiator:str='operator')->Revision:
        current=self.current(); parent=current.revision_id if current else ''
        r=Revision(revision_id=str(uuid.uuid4()),parent_revision_id=parent,command_id=command_id,
                   idempotency_key=idempotency_key or str(uuid.uuid4()),hashes=component_hashes(candidate),
                   candidate=candidate,initiator=initiator)
        self.save(r); atomic_write_json(self.desired_path,r.to_dict()); return r
    def save(self,r:Revision)->Revision:
        r.updated_at=time.time(); atomic_write_json(self._path(r.revision_id),r.to_dict()); return r
    def load(self,rid:str)->Revision|None:
        d=read_json(self._path(rid)); return revision_from_dict(d) if d else None
    def current(self)->Revision|None:
        d=read_json(self.current_path); return revision_from_dict(d) if d else None
    def desired(self)->Revision|None:
        d=read_json(self.desired_path); return revision_from_dict(d) if d else None
    def set_status(self,r:Revision,status:RevisionStatus,error:dict[str,Any]|None=None)->Revision:
        r.status=status; r.error=error; return self.save(r)
    def acknowledge(self,r:Revision,ack:ParticipantAck)->Revision:
        if ack.revision_id!=r.revision_id: raise RevisionError('Acknowledgement revision mismatch')
        r.acknowledgements[ack.participant]={
            'participant':ack.participant,'revision_id':ack.revision_id,'accepted':ack.accepted,
            'observed_hashes':ack.observed_hashes,'timestamp':ack.timestamp,'message':ack.message,'details':ack.details}
        return self.save(r)
    def commit(self,r:Revision,participants:tuple[str,...]=('ros','sionna','isaac'))->Revision:
        missing=[]; mismatch=[]
        for name in participants:
            ack=r.acknowledgements.get(name)
            if not ack or not ack.get('accepted'): missing.append(name); continue
            observed=ack.get('observed_hashes') or {}
            for key,val in r.hashes.items():
                if key in observed and observed[key]!=val: mismatch.append(f'{name}:{key}')
        if missing: raise RevisionError(f'Missing participant acknowledgement: {", ".join(missing)}')
        if mismatch: raise RevisionError(f'Observed-state hash mismatch: {", ".join(mismatch)}')
        r.status=RevisionStatus.COMMITTED; self.save(r); atomic_write_json(self.current_path,r.to_dict()); return r
    def rollback(self,rid:str)->Revision:
        target=self.load(rid)
        if not target: raise RevisionError(f'Unknown revision {rid}')
        candidate=self.create(target.candidate,command_id='rollback',initiator='operator')
        candidate.status=RevisionStatus.ROLLED_BACK; return self.save(candidate)

def revision_from_dict(d:dict[str,Any])->Revision:
    return Revision(revision_id=d['revision_id'],parent_revision_id=d.get('parent_revision_id',''),
                    command_id=d.get('command_id',''),idempotency_key=d.get('idempotency_key',''),
                    hashes=d.get('hashes',{}),candidate=d.get('candidate',{}),
                    status=RevisionStatus(d.get('status','DRAFT_SAVED')),initiator=d.get('initiator','operator'),
                    created_at=float(d.get('created_at',time.time())),updated_at=float(d.get('updated_at',time.time())),
                    acknowledgements=d.get('acknowledgements',{}),error=d.get('error'),
                    retry_count=int(d.get('retry_count',0)),scene_checksum=d.get('scene_checksum',''))

# ---------------------------------------------------------------------------
# Compatibility and higher-level reconciliation manager
# ---------------------------------------------------------------------------
from dataclasses import dataclass
from .models import ParticipantState
from .state import StateStore


@dataclass(frozen=True)
class RevisionPaths:
    results: Path
    revisions: Path
    desired: Path
    committed: Path
    reconciliation: Path
    ros_ack: Path
    sionna_ack: Path
    isaac_ack: Path


class RevisionManager:
    """Dict-based revision manager used by the HTTP API and diagnostics.

    ``RevisionStore`` remains the typed low-level store.  This facade provides
    the complete desired/observed reconciliation contract used by the
    brownfield API, including exact per-domain drift reporting.
    """

    REQUIRED_PARTICIPANTS = ("ros", "sionna", "isaac")

    def __init__(self, root: str | Path):
        root_path = Path(root).resolve()
        runtime_paths = StateStore(root_path).paths
        self.paths = RevisionPaths(
            results=runtime_paths.results,
            revisions=ensure_shared_directory(runtime_paths.revisions),
            desired=runtime_paths.desired_revision,
            committed=runtime_paths.committed_revision,
            reconciliation=runtime_paths.reconciliation,
            ros_ack=runtime_paths.ros_revision_ack,
            sionna_ack=runtime_paths.sionna_revision_ack,
            isaac_ack=runtime_paths.isaac_ack,
        )

    def desired(self) -> dict[str, Any]:
        return read_json(self.paths.desired, {}) or {}

    def committed(self) -> dict[str, Any]:
        return read_json(self.paths.committed, {}) or {}

    def current(self) -> dict[str, Any]:
        return self.committed()

    def summary(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "revision_id": record.get("revision_id"),
            "parent_revision_id": record.get("parent_revision_id"),
            "phase": record.get("phase"),
            "state": record.get("state"),
            "hashes": record.get("hashes", {}),
            "required_participants": record.get("required_participants", list(self.REQUIRED_PARTICIPANTS)),
            "affected_entities": record.get("affected_entities", []),
            "updated_at": record.get("updated_at"),
        }

    def _path(self, revision_id: str) -> Path:
        return self.paths.revisions / f"{revision_id}.json"

    def create(
        self,
        candidate: dict[str, Any],
        *,
        reason: str,
        command_id: str = "",
        idempotency_key: str = "",
        initiator: str = "operator",
        required_participants: tuple[str, ...] = ("ros", "sionna", "isaac"),
        affected_entities: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        current = read_json(self.paths.committed, {}) or {}
        revision_id = str(uuid.uuid4())
        record: dict[str, Any] = {
            "revision_id": revision_id,
            "parent_revision_id": str(current.get("revision_id", "")),
            "command_id": command_id,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
            "reason": reason,
            "initiator": initiator,
            "phase": "DRAFT_SAVED",
            "state": "PENDING_ROS",
            "created_at": time.time(),
            "updated_at": time.time(),
            "hashes": component_hashes(candidate),
            "candidate": candidate,
            "config": candidate,
            "required_participants": list(required_participants),
            "affected_entities": list(affected_entities),
            "participants": {
                name: {
                    "state": ParticipantState.PENDING.value,
                    "observed_revision": "",
                    "observed_hashes": {},
                    "message": "",
                    "timestamp": None,
                }
                for name in required_participants
            },
            "retry_count": 0,
            "error": None,
        }
        self.write(record)
        atomic_write_json(self.paths.desired, record)
        self._write_reconciliation(record)
        return record

    def write(self, record: dict[str, Any]) -> dict[str, Any]:
        record = dict(record)
        record["updated_at"] = time.time()
        atomic_write_json(self._path(str(record["revision_id"])), record)
        return record

    def read(self, revision_id: str) -> dict[str, Any]:
        value = read_json(self._path(revision_id), {}) or {}
        if not value:
            raise RuntimeError(f"Unknown revision {revision_id}")
        return value

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        records = [read_json(path, {}) or {} for path in self.paths.revisions.glob("*.json")]
        return sorted(records, key=lambda item: float(item.get("updated_at", 0)), reverse=True)[:limit]

    def mark_participant(
        self,
        revision_id: str,
        participant: str,
        *,
        state: ParticipantState | str,
        observed_revision: str = "",
        observed_hashes: dict[str, str] | None = None,
        message: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if participant not in self.REQUIRED_PARTICIPANTS:
            raise RuntimeError(f"Unknown revision participant {participant}")
        record = self.read(revision_id)
        state_value = state.value if isinstance(state, ParticipantState) else str(state)
        record.setdefault("participants", {})[participant] = {
            "state": state_value,
            "observed_revision": observed_revision,
            "observed_hashes": dict(observed_hashes or {}),
            "message": message,
            "details": dict(details or {}),
            "timestamp": time.time(),
        }
        sequence = {"ros": "PENDING_SIONNA", "sionna": "PENDING_ISAAC", "isaac": "IN_SYNC"}
        if state_value == ParticipantState.ACKNOWLEDGED.value:
            record["state"] = sequence[participant]
            record["phase"] = f"APPLIED_TO_{participant.upper()}"
        elif state_value == ParticipantState.FAILED.value:
            record["state"] = "FAILED"
            record["phase"] = "FAILED"
        self.write(record)
        self._write_reconciliation(record)
        return record

    @staticmethod
    def _ack_drift(record: dict[str, Any], ack: dict[str, Any]) -> dict[str, Any]:
        expected_revision = str(record.get("revision_id", ""))
        observed_revision = str(ack.get("revision_id") or ack.get("revision") or "")
        observed_hashes = ack.get("applied_hashes") or ack.get("observed_hashes") or ack.get("hashes") or {}
        hash_mismatches: dict[str, dict[str, Any]] = {}
        for key, expected in (record.get("hashes") or {}).items():
            if key not in observed_hashes:
                hash_mismatches[key] = {
                    "expected": expected,
                    "observed": None,
                    "reason": "MISSING",
                }
            elif observed_hashes[key] != expected:
                hash_mismatches[key] = {
                    "expected": expected,
                    "observed": observed_hashes[key],
                    "reason": "MISMATCH",
                }
        return {
            "revision_mismatch": bool(observed_revision and observed_revision != expected_revision),
            "expected_revision": expected_revision,
            "observed_revision": observed_revision,
            "hash_mismatches": hash_mismatches,
        }

    def all_required_acknowledged(self, record: dict[str, Any]) -> bool:
        expected = record.get("hashes") or {}
        required = tuple(record.get("required_participants") or self.REQUIRED_PARTICIPANTS)
        for name in required:
            participant = (record.get("participants") or {}).get(name) or {}
            if participant.get("state") != ParticipantState.ACKNOWLEDGED.value:
                return False
            if participant.get("observed_revision") != record.get("revision_id"):
                return False
            observed = participant.get("observed_hashes") or {}
            if any(observed.get(key) != value for key, value in expected.items()):
                return False
        return True

    def commit(self, revision_id: str) -> dict[str, Any]:
        record = self.read(revision_id)
        if not self.all_required_acknowledged(record):
            raise RuntimeError("Revision cannot commit before all matching participant acknowledgements")
        record["phase"] = "COMMITTED"
        record["state"] = "IN_SYNC"
        record = self.write(record)
        atomic_write_json(self.paths.committed, record)
        atomic_write_json(self.paths.desired, record)
        self._write_reconciliation(record)
        return record

    def rollback(self, revision_id: str) -> dict[str, Any]:
        target = self.read(revision_id)
        record = self.create(
            target.get("candidate", {}),
            reason=f"rollback_to:{revision_id}",
            command_id="rollback",
        )
        record["phase"] = "ROLLED_BACK"
        record["state"] = "ROLLED_BACK"
        return self.write(record)

    def _participant_ack_files(self) -> dict[str, Path]:
        return {
            "ros": self.paths.ros_ack,
            "sionna": self.paths.sionna_ack,
            "isaac": self.paths.isaac_ack,
        }

    def status(self, revision_id: str | None = None, *, refresh: bool = True) -> dict[str, Any]:
        if revision_id:
            record = self.read(revision_id)
        else:
            record = read_json(self.paths.desired, {}) or read_json(self.paths.committed, {}) or {}
        if not record:
            return {
                "state": "NO_REVISION",
                "in_sync": False,
                "pending_participants": list(self.REQUIRED_PARTICIPANTS),
                "drift_participants": [],
                "drift_details": {},
            }

        participants = record.get("participants") or {}
        required = tuple(record.get("required_participants") or self.REQUIRED_PARTICIPANTS)
        pending = [
            name
            for name in required
            if (participants.get(name) or {}).get("state") != ParticipantState.ACKNOWLEDGED.value
        ]
        drift_details: dict[str, Any] = {}
        for name, path in self._participant_ack_files().items():
            ack = read_json(path, {}) or {}
            if not ack:
                continue
            detail = self._ack_drift(record, ack)
            if detail["revision_mismatch"] or detail["hash_mismatches"]:
                drift_details[name] = detail
        state = str(record.get("state") or record.get("phase") or "PENDING_ROS")
        if drift_details:
            state = "DRIFT_DETECTED"
        elif not pending and self.all_required_acknowledged(record):
            state = "IN_SYNC" if record.get("phase") == "COMMITTED" else "READY_TO_COMMIT"
        result = {
            "revision_id": record.get("revision_id"),
            "state": state,
            "phase": record.get("phase"),
            "in_sync": state == "IN_SYNC",
            "pending_participants": pending,
            "participants": participants,
            "drift_participants": sorted(drift_details),
            "drift_details": drift_details,
            "hashes": record.get("hashes", {}),
            "updated_at": record.get("updated_at"),
        }
        atomic_write_json(self.paths.reconciliation, result)
        return result

    def _write_reconciliation(self, record: dict[str, Any]) -> None:
        atomic_write_json(
            self.paths.reconciliation,
            {
                "revision_id": record.get("revision_id"),
                "state": record.get("state"),
                "phase": record.get("phase"),
                "participants": record.get("participants", {}),
                "hashes": record.get("hashes", {}),
                "updated_at": time.time(),
            },
        )
