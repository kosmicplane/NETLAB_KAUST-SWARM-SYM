from __future__ import annotations
from dataclasses import dataclass
from .research_tools import rotary_wing_power_w
@dataclass
class EnergyState:
 capacity_wh:float;remaining_wh:float;propulsion_j:float=0;communication_j:float=0;computing_j:float=0;payload_j:float=0
 @property
 def soc_pct(self):return max(0.0,min(100.0,100*self.remaining_wh/self.capacity_wh)) if self.capacity_wh>0 else 0.0
 def consume(self,dt_s:float,*,speed_mps:float=0,communication_w:float=0,computing_w:float=0,payload_w:float=0):
  if dt_s<0:raise ValueError('dt must be non-negative')
  p=rotary_wing_power_w(speed_mps);self.propulsion_j+=p*dt_s;self.communication_j+=communication_w*dt_s;self.computing_j+=computing_w*dt_s;self.payload_j+=payload_w*dt_s
  self.remaining_wh=max(0.0,self.remaining_wh-(p+communication_w+computing_w+payload_w)*dt_s/3600);return self
 def metrics(self,delivered_bits:float=0,distance_m:float=0):
  total=self.propulsion_j+self.communication_j+self.computing_j+self.payload_j
  return {'soc_pct':self.soc_pct,'total_energy_j':total,'propulsion_energy_j':self.propulsion_j,'communication_energy_j':self.communication_j,'computing_energy_j':self.computing_j,'payload_energy_j':self.payload_j,'energy_per_delivered_bit_j':total/delivered_bits if delivered_bits>0 else None,'energy_per_m_j':total/distance_m if distance_m>0 else None}
