from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
import shutil,subprocess
@dataclass
class AdapterCapability:
 id:str;purpose:str;executable:str;time_ownership:str;data_contract:str;enabled:bool=False
 def available(self):return shutil.which(self.executable) is not None
 def describe(self):return asdict(self)|{'available':self.available()}
ADAPTERS={
 'ns3_5g_lena':AdapterCapability('ns3_5g_lena','5G NR protocol/system simulation','ns3','NETLAB or conservative lockstep','revisioned mobility/link/packet events'),
 'simu5g':AdapterCapability('simu5g','OMNeT++/MEC protocol simulation','opp_run','co-simulation coordinator','FMI/gRPC/event trace'),
 'fmi':AdapterCapability('fmi','Model exchange and co-simulation','fmpy','FMI master','FMI 3.x FMU'),
 'helics':AdapterCapability('helics','Multi-domain time coordination','helics_app','HELICS broker','HELICS messages'),
 'px4_sitl':AdapterCapability('px4_sitl','Autopilot SITL execution','px4','PX4/ROS clock bridge','uORB/MAVLink/ROS 2'),
}
def adapter_matrix():return {k:v.describe() for k,v in ADAPTERS.items()}
