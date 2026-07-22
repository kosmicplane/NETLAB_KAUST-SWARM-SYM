from __future__ import annotations
import heapq,random
from dataclasses import dataclass,field
from enum import Enum
class PacketStatus(str,Enum):CREATED='CREATED';QUEUED='QUEUED';WAITING_FOR_LINK='WAITING_FOR_LINK';TRANSMITTING='TRANSMITTING';ADVANCED='ADVANCED';DELIVERED='DELIVERED';PAUSED_OUTAGE='PAUSED_OUTAGE';RETRYING='RETRYING';DROPPED='DROPPED';EXPIRED='EXPIRED';CANCELLED='CANCELLED'
@dataclass(order=True)
class QueuedPacket:
 sort_key:tuple=field(init=False,repr=False);priority:int;created_at:float;packet_id:str;flow_id:str;size_bytes:int;deadline_s:float|None=None;status:PacketStatus=PacketStatus.CREATED
 def __post_init__(self):self.sort_key=(-self.priority,self.created_at);self.status=PacketStatus.QUEUED
class PacketQueue:
 def __init__(self,capacity:int=128,discipline:str='fifo'):self.capacity=capacity;self.discipline=discipline;self._items=[];self.dropped=0
 def push(self,p:QueuedPacket)->bool:
  if len(self._items)>=self.capacity:self.dropped+=1;p.status=PacketStatus.DROPPED;return False
  if self.discipline=='priority':heapq.heappush(self._items,p)
  else:self._items.append(p)
  return True
 def pop(self)->QueuedPacket|None:
  if not self._items:return None
  return heapq.heappop(self._items) if self.discipline=='priority' else self._items.pop(0)
 def __len__(self):return len(self._items)
def next_arrival(model:str,rate:float,rng:random.Random)->float:
 if rate<=0:raise ValueError('rate must be positive')
 if model in {'constant_packet_rate','constant_bit_rate'}:return 1/rate
 if model=='poisson':return rng.expovariate(rate)
 if model=='bursty_on_off':return rng.expovariate(rate*2) if rng.random()<.7 else rng.expovariate(rate*.2)
 raise ValueError(f'unsupported generation model {model}')
