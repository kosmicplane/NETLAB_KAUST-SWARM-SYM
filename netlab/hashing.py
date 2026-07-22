from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

def canonical_json(value: Any) -> bytes:
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')

def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()

def sha256_file(path: str|Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def component_hashes(config:dict[str,Any]) -> dict[str,str]:
    keys=('topology','swarm','antennas','world','traffic','failures')
    out={'config_hash':sha256_value(config)}
    for key in keys: out[f'{key.rstrip("s")}_hash' if key=='failures' else f'{key}_hash']=sha256_value(config.get(key,{}))
    # stable canonical names expected by the synchronization protocol
    out['topology_hash']=sha256_value(config.get('topology',{}))
    out['swarm_hash']=sha256_value(config.get('swarm',{}))
    out['antenna_hash']=sha256_value(config.get('antennas',{}))
    out['world_hash']=sha256_value(config.get('world',{}))
    out['traffic_hash']=sha256_value(config.get('traffic',{}))
    out['failure_hash']=sha256_value(config.get('failures',{}))
    return out
