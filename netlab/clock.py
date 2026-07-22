from __future__ import annotations
import time
from dataclasses import dataclass
from enum import Enum
class ClockMode(str,Enum):REAL_TIME='REAL_TIME';FIXED_STEP='FIXED_STEP';ACCELERATED='ACCELERATED';REPLAY='REPLAY'
@dataclass
class SimulationClock:
 mode:ClockMode=ClockMode.REAL_TIME;step_s:float=1/60;scale:float=1.0;sim_time_s:float=0.0;paused:bool=False
 def __post_init__(self):self._wall_start=time.monotonic();self._sim_start=self.sim_time_s
 def now(self)->float:
  if self.mode==ClockMode.REAL_TIME and not self.paused:return self._sim_start+(time.monotonic()-self._wall_start)*self.scale
  return self.sim_time_s
 def tick(self,steps:int=1)->float:
  if not self.paused or self.mode in {ClockMode.FIXED_STEP,ClockMode.REPLAY}:self.sim_time_s=self.now()+self.step_s*steps
  return self.sim_time_s
 def pause(self):self.sim_time_s=self.now();self.paused=True
 def resume(self):self._sim_start=self.sim_time_s;self._wall_start=time.monotonic();self.paused=False
 def reset(self,t:float=0):self.sim_time_s=t;self._sim_start=t;self._wall_start=time.monotonic()
 def real_time_factor(self)->float:
  wall=max(1e-12,time.monotonic()-self._wall_start);return max(0.0,(self.now()-self._sim_start)/wall)
