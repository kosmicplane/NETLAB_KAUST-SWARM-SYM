"""Research-grade analytical utilities with explicit assumptions and provenance."""
from __future__ import annotations
import csv, math, statistics
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence, Any

C=299_792_458.0
K_B=1.380649e-23

@dataclass
class ModelResult:
    model:str; version:str; fidelity:str; values:dict[str,float]; assumptions:list[str]; validity_domain:str; source:str
    def to_dict(self): return asdict(self)

def fspl_db(distance_m:float,frequency_hz:float)->float:
    if distance_m<=0 or frequency_hz<=0: raise ValueError('distance and frequency must be positive')
    return 20*math.log10(4*math.pi*distance_m*frequency_hz/C)

def thermal_noise_dbm(bandwidth_hz:float,noise_figure_db:float=0.0,temperature_k:float=290.0)->float:
    if bandwidth_hz<=0 or temperature_k<=0: raise ValueError('bandwidth and temperature must be positive')
    watts=K_B*temperature_k*bandwidth_hz
    return 10*math.log10(watts*1000)+noise_figure_db

def shannon_capacity_mbps(bandwidth_hz:float,sinr_db:float,efficiency:float=1.0)->float:
    if bandwidth_hz<=0 or not 0<efficiency<=1: raise ValueError('invalid bandwidth or efficiency')
    return efficiency*bandwidth_hz*math.log2(1+10**(sinr_db/10))/1e6

def probabilistic_a2g_path_loss(distance_2d_m:float,altitude_m:float,frequency_hz:float,
                               environment:str='urban')->ModelResult:
    params={'suburban':(4.88,0.43,0.1,21.0),'urban':(9.61,0.16,1.0,20.0),
            'dense_urban':(12.08,0.11,1.6,23.0),'highrise':(27.23,0.08,2.3,34.0)}
    if environment not in params: raise ValueError(f'unsupported environment {environment}')
    if distance_2d_m<0 or altitude_m<=0: raise ValueError('invalid geometry')
    a,b,eta_los,eta_nlos=params[environment]
    d3=math.hypot(distance_2d_m,altitude_m); elevation=math.degrees(math.atan2(altitude_m,max(distance_2d_m,1e-9)))
    p_los=1/(1+a*math.exp(-b*(elevation-a)))
    loss=fspl_db(d3,frequency_hz)+p_los*eta_los+(1-p_los)*eta_nlos
    return ModelResult('probabilistic_air_to_ground','1.0','F2_STOCHASTIC',
      {'distance_3d_m':d3,'elevation_deg':elevation,'los_probability':p_los,'path_loss_db':loss},
      ['statistical environment class','no deterministic obstruction geometry'],
      'macro-scale air-to-ground planning; not a substitute for ray tracing',
      'Al-Hourani-style probabilistic LoS model')

def ntn_slant_range_delay(altitude_m:float,elevation_deg:float,earth_radius_m:float=6_371_000.0)->ModelResult:
    if altitude_m<=0 or not 0<elevation_deg<=90: raise ValueError('invalid altitude or elevation')
    e=math.radians(elevation_deg); r=earth_radius_m; h=altitude_m
    slant=math.sqrt((r+h)**2-(r*math.cos(e))**2)-r*math.sin(e)
    delay=slant/C
    return ModelResult('spherical_earth_slant_range','1.0','F1_ANALYTICAL',
      {'slant_range_m':slant,'one_way_delay_s':delay,'round_trip_delay_s':2*delay},
      ['spherical Earth','no atmospheric refraction'],
      'first-order NTN geometry', '3GPP/ITU-compatible geometry reference')

def rotary_wing_power_w(speed_mps:float,*,p0:float=79.86,pi:float=88.63,u_tip:float=120.0,
                        v0:float=4.03,d0:float=0.6,rho:float=1.225,s:float=0.05,area:float=0.503)->float:
    if speed_mps<0: raise ValueError('speed must be non-negative')
    v=speed_mps
    profile=p0*(1+3*v*v/(u_tip*u_tip))
    induced=pi*math.sqrt(math.sqrt(1+v**4/(4*v0**4))-v*v/(2*v0*v0))
    parasite=0.5*d0*rho*s*area*v**3
    return profile+induced+parasite

def edge_offloading(local_cycles:float,cpu_local_hz:float,input_bits:float,uplink_mbps:float,
                    edge_cpu_hz:float,output_bits:float=0,downlink_mbps:float|None=None,
                    tx_power_w:float=1.0,local_energy_coeff:float=1e-28)->ModelResult:
    vals=[local_cycles,cpu_local_hz,input_bits,uplink_mbps,edge_cpu_hz]
    if any(v<=0 for v in vals): raise ValueError('positive parameters required')
    local_delay=local_cycles/cpu_local_hz
    local_energy=local_energy_coeff*local_cycles*cpu_local_hz**2
    upload=input_bits/(uplink_mbps*1e6); edge=local_cycles/edge_cpu_hz
    download=0 if output_bits<=0 else output_bits/((downlink_mbps or uplink_mbps)*1e6)
    offload_delay=upload+edge+download; offload_energy=tx_power_w*upload
    return ModelResult('edge_offloading_budget','1.0','F1_ANALYTICAL',
      {'local_delay_s':local_delay,'local_energy_j':local_energy,'offload_delay_s':offload_delay,
       'offload_energy_j':offload_energy,'latency_gain_s':local_delay-offload_delay,'energy_gain_j':local_energy-offload_energy},
      ['single task','no queueing unless supplied externally'], 'task-offloading comparison', 'analytical MEC task budget')

def jain_fairness(values:Sequence[float])->float:
    if not values or any(v<0 for v in values): raise ValueError('non-negative non-empty values required')
    s=sum(values); q=sum(v*v for v in values); return 0.0 if q==0 else s*s/(len(values)*q)

def age_of_information(receive_times:Sequence[float],generation_times:Sequence[float])->dict[str,float]:
    if len(receive_times)!=len(generation_times) or not receive_times: raise ValueError('matching non-empty sequences required')
    a=[max(0.0,r-g) for r,g in zip(receive_times,generation_times)]
    return {'mean_aoi_s':statistics.fmean(a),'peak_aoi_s':max(a),'p95_aoi_s':sorted(a)[max(0,math.ceil(.95*len(a))-1)]}

def calibrate_log_distance(samples:Iterable[tuple[float,float]],frequency_hz:float)->dict[str,float]:
    pairs=[(d,pl) for d,pl in samples if d>0]
    if len(pairs)<2: raise ValueError('at least two samples required')
    x=[math.log10(d) for d,_ in pairs]; y=[pl-fspl_db(1.0,frequency_hz) for _,pl in pairs]
    denom=sum(v*v for v in x)
    n=sum(a*b for a,b in zip(x,y))/(10*denom) if denom else 2.0
    residual=[pl-(fspl_db(1.0,frequency_hz)+10*n*math.log10(d)) for d,pl in pairs]
    sigma=statistics.pstdev(residual) if len(residual)>1 else 0.0
    return {'path_loss_exponent':n,'shadowing_sigma_db':sigma,'sample_count':len(pairs)}

def inverse_distance_radio_map(samples:Sequence[tuple[float,float,float]],points:Sequence[tuple[float,float]],power:float=2.0)->list[dict[str,float]]:
    if not samples: raise ValueError('samples required')
    out=[]
    for x,y in points:
        exact=[v for sx,sy,v in samples if math.hypot(x-sx,y-sy)<1e-12]
        if exact: val=exact[0]
        else:
            weights=[1/(math.hypot(x-sx,y-sy)**power) for sx,sy,_ in samples]
            val=sum(w*s[2] for w,s in zip(weights,samples))/sum(weights)
        out.append({'x':x,'y':y,'value':val})
    return out
