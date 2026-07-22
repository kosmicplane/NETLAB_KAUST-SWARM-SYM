import unittest
from netlab.topology_metrics import graph_metrics,articulation_points,bridges
class TestGraph(unittest.TestCase):
 def test_chain(self):
  n=list(range(4));e=[(0,1),(1,2),(2,3)];m=graph_metrics(n,e);self.assertEqual(m['connected_components'],1);self.assertEqual(m['diameter_hops'],3);self.assertEqual(set(m['articulation_points']),{1,2});self.assertEqual(len(m['bridges']),3)
 def test_cycle(self):
  m=graph_metrics(range(4),[(0,1),(1,2),(2,3),(3,0)]);self.assertFalse(m['articulation_points']);self.assertFalse(m['bridges'])
if __name__=='__main__':unittest.main()
