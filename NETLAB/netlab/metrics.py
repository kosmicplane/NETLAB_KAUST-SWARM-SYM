from __future__ import annotations
import math,statistics
from collections import defaultdict,deque
from dataclasses import dataclass,field
@dataclass
class MetricSample:
 name:str;value:float;unit:str;timestamp_wall:float;timestamp_sim:float;source:str;fidelity:str;model_version:str;quality:str='GOOD';uncertainty:float|None=None;tags:dict[str,str]=field(default_factory=dict)
class MetricRegistry:
 def __init__(self,max_samples:int=10000):self.max_samples=max_samples;self.data=defaultdict(lambda:deque(maxlen=max_samples))
 def add(self,s:MetricSample):self.data[s.name].append(s)
 def values(self,name):return [s.value for s in self.data.get(name,())]
 def summary(self,name):
  v=self.values(name)
  if not v:return {'count':0}
  q=sorted(v);pct=lambda p:q[min(len(q)-1,max(0,math.ceil(p*len(q))-1))]
  return {'count':len(v),'mean':statistics.fmean(v),'median':statistics.median(v),'stddev':statistics.pstdev(v) if len(v)>1 else 0,'min':min(v),'max':max(v),'p50':pct(.5),'p90':pct(.9),'p95':pct(.95),'p99':pct(.99)}
 def empirical_cdf(self,name):
  v=sorted(self.values(name));return [{'value':x,'cdf':(i+1)/len(v)} for i,x in enumerate(v)] if v else []
