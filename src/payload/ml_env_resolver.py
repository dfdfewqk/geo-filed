# -*- coding: utf-8 -*-
"""Read-only interpreter discovery for optional GeoField ML inference.

Never installs software, modifies environments, or reuses a failed interpreter.
CadQuery/scikit-learn R12 and PyTorch BrepMFR are separate capabilities.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from engine_runtime import engine_python, prepare_python_environment

_CACHE = {}
_LOCK = threading.Lock()
_TTL = 75


def _safe_path(value):
    try:
        path = Path(str(value).strip().strip('"')).expanduser()
        return path.resolve() if path.is_file() and path.suffix.lower() in ('.exe','', '.bin') else None
    except (ValueError, OSError, TypeError):
        return None


def candidates(env_key, primary=None):
    """Search explicitly configured, already installed environments only."""
    paths = []
    seen = set()
    def add(value):
        p = _safe_path(value)
        if p and str(p).casefold() not in seen:
            seen.add(str(p).casefold())
            paths.append(p)
    add(os.environ.get(env_key))
    if isinstance(primary, dict): add(primary.get('path'))
    local = Path(os.environ.get('LOCALAPPDATA', str(Path.home())))
    engines = local / 'GeoFieldCAD' / 'engines'
    # Existing engine runtime stores different interpreters for FEA and ML.
    # Do not use the Gmsh-only environment as a reason to report ML ready.
    for role in ('ml','fea'):
        marker = engines / ('engine-active-'+role+'-r12.json')
        if marker.is_file():
            try:
                record = json.loads(marker.read_text(encoding='utf-8'))
                prefix = Path(record['prefix']).resolve()
                scope = (engines/'r12-envs').resolve()
                if (record.get('role')==role and prefix.parent==scope and
                    prefix.name.startswith('geofield-'+role+'-r12-')):
                    add(prefix / 'python.exe')
            except (ValueError, TypeError, KeyError, OSError): pass
    root = engines / 'r12-envs'
    if root.is_dir():
        for pattern in ('geofield-ml-r12-*/python.exe','geofield-fea-r12-*/python.exe'):
            for p in sorted(root.glob(pattern),reverse=True)[:8]: add(p)
    add(engines / 'geofield-analysis-win64' / 'python.exe')
    for key in ('VIRTUAL_ENV','CONDA_PREFIX'):
        if os.environ.get(key):
            prefix=Path(os.environ[key])
            add(prefix/('Scripts/python.exe' if os.name=='nt' else 'bin/python'))
    add(sys.executable)
    add(shutil.which('python'))
    return paths[:22]


def _probe(path, modules, timeout=18):
    """Probe real imports, not just find_spec, so broken DLLs are caught."""
    program = ('import importlib,json; names='+repr(tuple(modules))+'; problems={};'
               '\nfor name in names:\n try:importlib.import_module(name)\n except Exception as ex:problems[name]=type(ex).__name__+": "+str(ex)[:180]'
               '\nprint(json.dumps({"ok":not problems,"errors":problems}))')
    kwargs = {'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
    try:
        proc=subprocess.run([str(path),'-c',program],capture_output=True,text=True,
                            errors='replace',timeout=timeout,
                            env=prepare_python_environment(str(path)),**kwargs)
        payload=json.loads(proc.stdout.strip().splitlines()[-1]) if proc.stdout.strip() else {}
        if proc.returncode==0 and payload.get('ok') is True:
            return {'ok':True,'path':str(path),'modules':{v:True for v in modules},'error':''}
        info=payload.get('errors') or {'process':(proc.stderr or proc.stdout or 'probe failed')[-250:]}
        return {'ok':False,'path':str(path),'modules':{v:info.get(v,True) for v in modules},'error':str(info)[:380]}
    except (OSError,subprocess.TimeoutExpired,ValueError,IndexError,TypeError) as exc:
        return {'ok':False,'path':str(path),'modules':{},'error':type(exc).__name__+': '+str(exc)[:200]}


def resolve(env_key, requirements):
    requirements=tuple(requirements)
    # engine_python uses existing registered configuration; reuse when healthy.
    try: primary=engine_python(env_key,requirements)
    except (OSError,ValueError,TypeError,RuntimeError) as exc:
        primary={'ok':False,'path':None,'modules':{},'error':str(exc)[:250]}
    if primary.get('ok') and _safe_path(primary.get('path')):
        return {**primary,'source':'existing_engine_runtime'}
    key=(env_key,requirements,os.environ.get(env_key),os.environ.get('LOCALAPPDATA'),sys.executable)
    with _LOCK:
        cached=_CACHE.get(key)
        if cached and time.monotonic()-cached[0]<_TTL:return dict(cached[1])
    attempts=[]
    deadline=time.monotonic()+55.0
    for path in candidates(env_key,primary)[:10]:
        remaining=deadline-time.monotonic()
        if remaining<3:
            attempts.append({"python":"[timeout]","error":"Overall R12 ML probe time limit"})
            break
        result=_probe(path,requirements,timeout=min(18,max(3,remaining)))
        if result['ok']:
            result['source']='verified_existing_python'
            result['attempted']=len(attempts)+1
            with _LOCK:_CACHE[key]=(time.monotonic(),result)
            return dict(result)
        attempts.append({'python':str(path),'error':result['error']})
    result={'ok':False,'path':None,'modules':primary.get('modules') or {},
            'error':str(primary.get('error') or 'No installed Python imports the required modules')[:350],
            'source':'none','attempted':len(attempts),'attempts':attempts[:8]}
    with _LOCK:_CACHE[key]=(time.monotonic(),result)
    return dict(result)
