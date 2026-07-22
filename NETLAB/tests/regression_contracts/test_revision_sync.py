import copy,tempfile,unittest
from pathlib import Path
from netlab.revisions import RevisionStore,RevisionError
from netlab.synchronization import SynchronizationCoordinator,ImmediateParticipant
from netlab.contracts import Command,CommandStatus,RevisionStatus
class TestRevision(unittest.TestCase):
 def cfg(self):return {'experiment':{'id':'x'},'topology':{'mode':'chain'},'swarm':{'drones':[]},'antennas':{},'world':{},'traffic':{},'failures':{}}
 def test_commit_requires_all(self):
  with tempfile.TemporaryDirectory() as td:
   s=RevisionStore(Path(td)/'s');c=SynchronizationCoordinator(s,[ImmediateParticipant('ros'),ImmediateParticipant('sionna'),ImmediateParticipant('isaac')],Path(td)/'r');r,cmd=c.apply(self.cfg(),command=Command('apply'));self.assertEqual(r.status,RevisionStatus.COMMITTED);self.assertEqual(cmd.status,CommandStatus.COMPLETED);self.assertEqual(set(r.acknowledgements),{'ros','sionna','isaac'})
 def test_disconnected_isaac_pending(self):
  with tempfile.TemporaryDirectory() as td:
   s=RevisionStore(Path(td)/'s');c=SynchronizationCoordinator(s,[ImmediateParticipant('ros'),ImmediateParticipant('sionna'),ImmediateParticipant('isaac',False)],Path(td)/'r');r,cmd=c.apply(self.cfg());self.assertEqual(r.status,RevisionStatus.DEGRADED);self.assertNotEqual(cmd.status,CommandStatus.COMPLETED);self.assertIsNone(s.current())
 def test_hash_drift(self):
  from netlab.contracts import ParticipantAck
  with tempfile.TemporaryDirectory() as td:
   s=RevisionStore(Path(td));r=s.create(self.cfg())
   for n in ('ros','sionna','isaac'):s.acknowledge(r,ParticipantAck(n,r.revision_id,True,dict(r.hashes)|({'config_hash':'bad'} if n=='isaac' else {})))
   with self.assertRaises(RevisionError):s.commit(r)
if __name__=='__main__':unittest.main()

class TestImmutableIsaacCandidate(unittest.TestCase):
    def test_candidate_contains_revision_metadata_and_signal_path(self):
        from netlab.synchronization import RuntimeSynchronizer
        from netlab.revisions import RevisionManager
        from netlab.config import default_experiment
        import tempfile
        from netlab.io import read_json
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for p in ('Docker/workspace/shared','Docker/workspace/results'):
                (root/p).mkdir(parents=True,exist_ok=True)
            manager=RevisionManager(root)
            record=manager.create(default_experiment(),reason='test',command_id='cmd-isaac-candidate')
            sync=RuntimeSynchronizer(root)
            # Call only the file-emission portion by forcing immediate timeout.
            sync._apply_isaac(record,0.01)
            candidate=read_json(root/'Docker/workspace/shared/revisions'/f"{record['revision_id']}.json",{})
            signal=read_json(root/'Docker/workspace/results/snaas_isaac_sync_signal.json',{})
            self.assertEqual(candidate['_netlab_revision']['revision_id'],record['revision_id'])
            self.assertEqual(candidate['_netlab_revision']['config_hash'],record['hashes']['config_hash'])
            self.assertEqual(signal['config_path'],str(root/'Docker/workspace/shared/revisions'/f"{record['revision_id']}.json"))
