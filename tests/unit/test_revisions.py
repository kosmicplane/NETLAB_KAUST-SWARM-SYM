import tempfile
import unittest
from pathlib import Path

from netlab.config import default_experiment
from netlab.models import ParticipantState
from netlab.revisions import RevisionManager


class RevisionTests(unittest.TestCase):
    def test_revision_cannot_commit_before_required_acknowledgements(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-1")
            with self.assertRaises(RuntimeError):
                manager.commit(record["revision_id"])
            self.assertEqual(set(manager.status(record["revision_id"])["pending_participants"]), {"ros", "sionna", "isaac"})

    def test_revision_commits_only_after_matching_acknowledgements(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-2")
            for participant in ("ros", "sionna", "isaac"):
                manager.mark_participant(
                    record["revision_id"], participant,
                    state=ParticipantState.ACKNOWLEDGED,
                    observed_revision=record["revision_id"],
                    observed_hashes=record["hashes"],
                )
            committed = manager.commit(record["revision_id"])
            self.assertEqual(committed["phase"], "COMMITTED")
            self.assertTrue(manager.status(record["revision_id"])["in_sync"])

    def test_observed_revision_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-3")
            for participant in ("ros", "sionna", "isaac"):
                manager.mark_participant(
                    record["revision_id"], participant,
                    state=ParticipantState.ACKNOWLEDGED,
                    observed_revision=record["revision_id"],
                    observed_hashes=record["hashes"],
                )
            manager.commit(record["revision_id"])
            from netlab.io import atomic_write_json
            atomic_write_json(manager.paths.isaac_ack, {"ready": True, "revision_id": "different-revision", "applied_hashes": record["hashes"]})
            status = manager.status(record["revision_id"], refresh=False)
            self.assertEqual(status["state"], "DRIFT_DETECTED")
            self.assertIn("isaac", status["drift_participants"])

    def test_revision_rejects_acknowledgement_with_missing_component_hashes(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-missing-hashes")
            for participant in ("ros", "sionna", "isaac"):
                manager.mark_participant(
                    record["revision_id"], participant,
                    state=ParticipantState.ACKNOWLEDGED,
                    observed_revision=record["revision_id"],
                    observed_hashes={"config_hash": record["hashes"]["config_hash"]},
                )
            with self.assertRaises(RuntimeError):
                manager.commit(record["revision_id"])
            self.assertFalse(manager.all_required_acknowledged(manager.read(record["revision_id"])))

    def test_revision_rejects_acknowledgement_with_mismatched_domain_hash(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-bad-topology-hash")
            bad_hashes = dict(record["hashes"])
            bad_hashes["topology_hash"] = "stale-topology"
            manager.mark_participant(
                record["revision_id"], "ros",
                state=ParticipantState.ACKNOWLEDGED,
                observed_revision=record["revision_id"],
                observed_hashes=bad_hashes,
            )
            for participant in ("sionna", "isaac"):
                manager.mark_participant(
                    record["revision_id"], participant,
                    state=ParticipantState.ACKNOWLEDGED,
                    observed_revision=record["revision_id"],
                    observed_hashes=record["hashes"],
                )
            with self.assertRaises(RuntimeError):
                manager.commit(record["revision_id"])

    def test_observed_hash_drift_reports_exact_component(self):
        with tempfile.TemporaryDirectory() as td:
            manager = RevisionManager(Path(td))
            record = manager.create(default_experiment(), reason="test", command_id="cmd-hash-drift")
            for participant in ("ros", "sionna", "isaac"):
                manager.mark_participant(
                    record["revision_id"], participant,
                    state=ParticipantState.ACKNOWLEDGED,
                    observed_revision=record["revision_id"],
                    observed_hashes=record["hashes"],
                )
            manager.commit(record["revision_id"])
            from netlab.io import atomic_write_json
            bad_hashes = dict(record["hashes"])
            bad_hashes["world_hash"] = "out-of-date-world"
            atomic_write_json(manager.paths.isaac_ack, {
                "ready": True,
                "revision_id": record["revision_id"],
                "applied_hashes": bad_hashes,
            })
            status = manager.status(record["revision_id"], refresh=False)
            self.assertEqual(status["state"], "DRIFT_DETECTED")
            self.assertIn("isaac", status["drift_participants"])
            self.assertEqual(
                status["drift_details"]["isaac"]["hash_mismatches"]["world_hash"]["reason"],
                "MISMATCH",
            )


if __name__ == "__main__":
    unittest.main()
