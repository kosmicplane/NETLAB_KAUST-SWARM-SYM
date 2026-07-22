from __future__ import annotations
import hashlib, os, zipfile
from pathlib import Path
from typing import Iterable

class UnsafeAssetError(ValueError): pass

DEFAULT_EXTENSIONS={'.usd','.usda','.usdc','.obj','.fbx','.gltf','.glb','.json','.yaml','.yml','.csv','.geojson','.tif','.tiff','.dem','.png','.jpg','.jpeg'}

def validate_asset(path:str|Path,*,allowed:Iterable[str]=DEFAULT_EXTENSIONS,max_bytes:int=2_000_000_000)->dict:
    p=Path(path)
    if not p.is_file(): raise UnsafeAssetError('asset does not exist')
    if p.suffix.lower() not in set(allowed): raise UnsafeAssetError(f'unsupported extension {p.suffix}')
    size=p.stat().st_size
    if size>max_bytes: raise UnsafeAssetError('asset exceeds configured size limit')
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return {'path':str(p),'size_bytes':size,'sha256':h.hexdigest(),'trusted':False}

def safe_extract_zip(archive:str|Path,destination:str|Path,*,max_members:int=10000,max_total_bytes:int=5_000_000_000)->list[str]:
    src=Path(archive); dst=Path(destination); dst.mkdir(parents=True,exist_ok=True); total=0; names=[]
    with zipfile.ZipFile(src) as zf:
        infos=zf.infolist()
        if len(infos)>max_members: raise UnsafeAssetError('archive contains too many members')
        for info in infos:
            name=info.filename.replace('\\','/')
            parts=Path(name).parts
            if name.startswith('/') or '..' in parts: raise UnsafeAssetError(f'unsafe member {name}')
            total+=info.file_size
            if total>max_total_bytes: raise UnsafeAssetError('archive uncompressed size limit exceeded')
            target=(dst/name).resolve()
            if dst.resolve() not in target.parents and target!=dst.resolve(): raise UnsafeAssetError(f'path escape {name}')
            names.append(name)
        zf.extractall(dst)
    return names
