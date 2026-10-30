"""Probe already-installed Python interpreters for independent CAD/ML/FEA engines.

Never installs packages, runs untrusted code from CAD, or changes system settings.
A Python environment may be usable for BrepMFR independently of the Python
that runs the UI server. Use checked explicit worker interpreters, not guesses.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from functools import lru_cache

REQUIRED_ML = ('torch', 'numpy', 'OCP')
REQUIRED_GMSH = ('gmsh',)


def same_executable(a, b):
    try:
        return Path(a).resolve() == Path(b).resolve()
    except Exception:
        return str(a).casefold() == str(b).casefold()


@lru_cache(maxsize=32)
def probe_python(executable, modules, timeout=20):
    """Import real modules (find_spec alone misses native DLL errors)."""
    exe = Path(executable).expanduser()
    if not exe.is_file():
        return {'ok': False, 'path': str(exe), 'error': 'Python 실행 파일이 없습니다.', 'modules': {}}
    code = ('import importlib,json,sys; r={}; '
            'names='+repr(list(modules))+'; '
            '\nfor name in names:\n'
            ' try:\n  importlib.import_module(name); r[name]=True\n'
            ' except Exception as e:\n  r[name]=type(e).__name__+": "+str(e)[:260]\n'
            'print("GEOFIELD_PROBE_JSON="+json.dumps({"python":sys.executable,"modules":r}))')
    try:
        kwargs={'creationflags':getattr(subprocess,'CREATE_NO_WINDOW',0)} if os.name=='nt' else {}
        p=subprocess.run([str(exe),'-c',code],capture_output=True,text=True,
                         errors='replace',timeout=timeout,**kwargs)
        tag='GEOFIELD_PROBE_JSON='
        found=[v[len(tag):] for v in p.stdout.splitlines() if v.startswith(tag)]
        if p.returncode!=0 or not found:
            return {'ok': False,'path': str(exe),'error': ('Python 검사 실패: '+p.stderr[-450:]),'modules': {}}
        data=json.loads(found[-1]); data['path']=str(exe)
        data['ok']=all(data['modules'].get(k) is True for k in modules)
        return data
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:
        return {'ok': False,'path':str(exe),'modules':{},'error':str(e)[:300]}


def engine_python(envvar, modules):
    """Explicit interpreter must be valid; otherwise current Python is used."""
    override=os.environ.get(envvar,'').strip().strip('"')
    candidate=override if override else sys.executable
    return probe_python(str(Path(candidate).expanduser()),tuple(modules))


def gmsh_python_status():
    """Actual installed Gmsh import probe for isolated CI; no mocked solver."""
    data=engine_python('GEOFIELD_GMSH_PYTHON',REQUIRED_GMSH)
    data['selection']='ci_probed_python'
    return data
