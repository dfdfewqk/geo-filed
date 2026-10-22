# -*- coding: utf-8 -*-
"""GeoField R12.13 final validation: verified install + foreground backend start with persistent diagnostics.

Reads only the locally verified archive. It never installs dependencies,
modifies engineering files, or asserts a successful FEA calculation.
"""
from __future__ import annotations
import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
sys.dont_write_bytecode = True  # Keep staged package inventory unchanged.
import time
import traceback
import urllib.request
import webbrowser
from installer import apply, verify_bundle, DirectoryBundle, rollback_install
from geofield_port_recovery import stop_verified_old_geofield
from runtime_preflight import audit_runtime, status_summary

DIAG = Path(os.environ.get('GF_DIAG') or Path(os.environ.get('LOCALAPPDATA', '.')) / 'GeoFieldCAD' / 'diagnostics' / 'r12_launcher')

def emit(*parts):
    line = ' '.join(str(p) for p in parts)
    print(line, flush=True)
    try:
        DIAG.mkdir(parents=True, exist_ok=True)
        with (DIAG / 'bootstrap_latest.log').open('a', encoding='utf-8') as output:
            output.write(line + '\n')
    except OSError:
        pass

def _candidates():
    """Known local interpreters only; no dependency installation."""
    local = Path(os.environ['LOCALAPPDATA'])
    result = []
    def add(p):
        if p:
            path = Path(str(p).strip().strip('"')).expanduser()
            if path.is_file() and str(path).casefold() not in {str(x).casefold() for x in result}:
                result.append(path)
    add(os.environ.get('GEOFIELD_PYTHON'))
    add(local / 'GeoFieldCAD' / 'engines' / 'geofield-analysis-win64' / 'python.exe')
    for prefix in ('geofield-ml-r12-', 'geofield-fea-r12-'):
        root = local / 'GeoFieldCAD' / 'engines' / 'r12-envs'
        if root.is_dir():
            for p in sorted(root.glob(prefix + '*/python.exe'))[:12]: add(p)
    add(sys.executable)
    for name in ('python', 'python3'):
        add(shutil.which(name))
    for key in ('VIRTUAL_ENV','CONDA_PREFIX'):
        val = os.environ.get(key)
        if val: add(Path(val) / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python'))
    for base in (Path.home() / 'AppData' / 'Local' / 'Programs' / 'Python',
                 Path.home() / 'miniconda3' / 'envs', Path.home() / 'anaconda3' / 'envs'):
        if base.is_dir():
            for p in sorted(base.glob('*/python.exe'))[:12]: add(p)
    return result[:40]

def _choose_server(root):
    results = []
    fallback = None
    candidates = _candidates()
    if not candidates:
        raise RuntimeError('No installed Python interpreter was found. Nothing was downloaded.')
    deadline = time.monotonic() + 150.0
    for interpreter in candidates:
        remaining = deadline - time.monotonic()
        if remaining < 4:
            results.append(('[PROBE TIME LIMIT]', '150-second overall limit reached'))
            break
        emit('[PYTHON CHECK] Testing existing interpreter:', interpreter)
        try:
            check = subprocess.run([str(interpreter), '-u', str(root / 'GeoField_CAD_Analysis.py'), '--check'],
                                   cwd=str(root), capture_output=True, text=True, encoding='utf-8',
                                   errors='replace', timeout=min(28, max(3, int(remaining))))
            if check.returncode:
                results.append((str(interpreter), 'EXIT ' + str(check.returncode) + ': ' + (check.stderr or check.stdout)[-450:]))
                continue
            try:
                state = json.loads(check.stdout)
            except (ValueError, TypeError) as exc:
                results.append((str(interpreter), 'Invalid backend --check response: '+str(exc)[:140]))
                continue
            capabilities = state.get('capabilities', {})
            engine = capabilities.get('step_engine', 'missing')
            score = 3 if engine == 'OpenCASCADE/CadQuery' else (1 if capabilities.get('cad_analysis') else 0)
            results.append((str(interpreter), 'PASS engine=' + str(engine)))
            if score >= 3:
                for path, status in results: emit('[PYTHON PROBE]',path,status)
                return interpreter, results
            if score > 0 and fallback is None:
                fallback = interpreter
        except Exception as exc:
            results.append((str(interpreter), type(exc).__name__ + ': ' + str(exc)[:300]))
    for path, status in results: emit('[PYTHON PROBE]',path,status)
    if fallback is not None: return fallback, results
    raise RuntimeError('Existing GeoField Python engines could not start this backend. See [PYTHON PROBE] above. No engine packages were installed.')

def _ready(port, expected_version='R20-core-stabilization'):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/status', timeout=1.3) as response:
            if response.status != 200: return False
            data = json.loads(response.read(100000))
            return data.get('ok') is True and data.get('version') == expected_version
    except (OSError,ValueError,TimeoutError,KeyError): return False

def _port_occupied(port=8600):
    """A bound local port may be another program; never kill it automatically."""
    with socket.socket() as sock:
        sock.settimeout(0.7)
        return sock.connect_ex(('127.0.0.1',port)) == 0

def wait_for_port_release(max_wait=15, interval=1):
    """Release a confirmed old GeoField backend only; never stop unknown apps.

    Existing solver children prevent automatic closure. No installed files are
    changed until the listener has actually released the port.
    """
    if not _port_occupied():
        emit('[PORT] 8600 is available; safe to proceed with installation.')
        return True
    emit('[PORT] 8600 occupied: checking whether the owner is an old GeoField backend.')
    root = Path(os.environ['LOCALAPPDATA']) / 'GeoFieldCAD' / 'onefile_runtime' / '8a9ac53a821a0eb5'
    if stop_verified_old_geofield(root, emit):
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            if not _port_occupied():
                emit('[PORT] Previous server released 8600; proceeding with protected update.')
                return True
            time.sleep(interval)
    emit('[STOP] Port 8600 is in use by an unverified or still active process.')
    emit('[SAFE] No GeoField source or engineering files have been changed.')
    emit('[NEXT] No automatic termination of unknown processes or active solver children.')
    return False

def _start_backend(root, interpreter):
    if _ready(8600):
        # Installer will reject a live server; don't attach to potentially stale results.
        raise RuntimeError('A GeoField server already runs on port 8600; close it before R12 integration.')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', 8600)) == 0:
            raise RuntimeError('Port 8600 is occupied by an unverified process. Close that program before retrying.')
    DIAG.mkdir(parents=True,exist_ok=True)
    log = DIAG / 'backend_latest.log'
    # Open a dedicated log so no error is hidden if the browser tab appears then vanishes.
    with log.open('wb') as out:
        env = os.environ.copy()
        env['PYTHONUTF8'] = '1'
        env['PYTHONIOENCODING'] = 'utf-8'
        process = subprocess.Popen([str(interpreter), '-u', str(root / 'GeoField_CAD_Analysis.py'), '--port', '8600', '--no-browser'],
                                   cwd=str(root), env=env, stdout=out, stderr=subprocess.STDOUT)
        started = False
        for _ in range(300):
            if process.poll() is not None: break
            if _ready(8600): started = True; break
            time.sleep(0.2)
        if not started:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=6)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=6)
            emit('[ERROR] Backend never became ready. Exit code:',process.returncode)
            emit('[ERROR] Backend output:',log)
            if log.exists(): emit(log.read_text('utf-8',errors='replace')[-7000:])
            return 31
        emit('[READY] GeoField browser:', 'http://127.0.0.1:8600/')
        # R12 and the legacy BrepMFR are independent: never claim that a visible
        # CAD/FEA browser means either of the two ML engines is ready.
        try:
            url='http://127.0.0.1:8600/api/ml/r12/preflight'
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=6) as response:
                ml=json.loads(response.read(100000))
            emit('[R12 ML]', 'READY (research only)' if ml.get('available') else 'UNAVAILABLE',
                 '; '.join(str(x) for x in ml.get('missing',[]))[:1000])
        except Exception as exc:
            emit('[R12 ML] status check failed:',str(exc)[:350])
        emit('[LOG] Backend:', log)
        emit('[NOTICE] Keep this CMD window open while using the app; close with Ctrl+C when finished.')
        try: webbrowser.open('http://127.0.0.1:8600/')
        except Exception as exc: emit('[NOTICE] Browser open failed:',exc,'Open the URL manually.')
        try:
            while process.poll() is None:
                time.sleep(0.8)
        except KeyboardInterrupt:
            emit('[STOP] GeoField stopped by user.')
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=8)
            return 0
        emit('[EXIT] Backend exited. Exit code:', process.returncode)
        if process.returncode:
            emit('[ERROR] Backend output:',log)
            emit(log.read_text('utf-8',errors='replace')[-7000:])
        return 0 if process.returncode == 0 else 32

def check_mesh_series_runtime(root):
    """Ensure the installed CAD/FEA/ML dependency files exist before upgrade.

    Only checks file presence and symlinks; never runs an FEA calculation.
    """
    report = audit_runtime(root)
    if not report['ready_for_update']:
        raise RuntimeError('Required GeoField runtime dependency check failed: ' +
                           status_summary(report))
    return True

def main(args):
    """Verify -> stop old instance -> probe -> install -> start or revert."""
    package = Path(__file__).resolve().parent
    bundle = DirectoryBundle(package)
    audit_only = '--audit-runtime' in args[1:]
    if not audit_only:
        emit('[STEP 1/5] Verify all package files and SHA-256 hashes')
    manifest = verify_bundle(bundle)
    if audit_only:
        # No log directory, network calls or installation; return structured
        # diagnostics before stopping any running backend process.
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise RuntimeError('Windows LOCALAPPDATA missing.')
        root = Path(local) / 'GeoFieldCAD' / 'onefile_runtime' / manifest['runtime_id']
        report = audit_runtime(root)
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
        return 0 if report['ready_for_update'] else 24
    if '--verify-only' in args[1:]:
        emit('[OK] Package integrity verified. No installation or server changes.')
        return 0
    if not os.environ.get('LOCALAPPDATA'):
        raise RuntimeError('Windows LOCALAPPDATA missing; no files were modified.')
    DIAG.mkdir(parents=True,exist_ok=True)
    (DIAG / 'bootstrap_latest.log').write_text(
        'GeoField R12.13 final validation '+datetime.datetime.now().isoformat(timespec='seconds')+'\n', encoding='utf-8')
    emit('[STEP 2/5] Check for an active GeoField server before changing code')
    if not wait_for_port_release():
        return 23
    root = Path(os.environ['LOCALAPPDATA']) / 'GeoFieldCAD' / 'onefile_runtime' / '8a9ac53a821a0eb5'
    emit('[STEP 3/5] Check required modules, then Python/CAD engine BEFORE any changes')
    check_mesh_series_runtime(root)
    interpreter, _ = _choose_server(root)
    emit('[PYTHON]', interpreter)
    emit('[STEP 4/5] Install verified files with backups and rollback enabled')
    receipt = {}
    try:
        result=apply(bundle,receipt=receipt)
    except RuntimeError as exc:
        if 'port 8600 is open' in str(exc):
            emit('[STOP] Another server started while verifying. No new code was installed.')
            emit('[NEXT] Stop the old server CMD, then retry.')
            return 23
        raise
    if result:
        raise RuntimeError('Installer refused an incompatible GeoField runtime')
    install_only='--install-only' in args[1:]
    emit('[STEP 5/5] Verify updated backend before optional launch')
    try:
        # The old code passed preflight; test the UPDATED code before starting it.
        result=subprocess.run([str(interpreter), '-u', str(root/'GeoField_CAD_Analysis.py'), '--check'],
            cwd=str(root),capture_output=True,text=True,encoding='utf8',errors='replace',timeout=35)
        if result.returncode != 0:
            raise RuntimeError('Updated backend --check failed: '+(result.stderr or result.stdout)[-1500:])
        state=json.loads(result.stdout)
        if not isinstance(state,dict) or 'capabilities' not in state:
            raise RuntimeError('Updated backend --check response invalid')
        if install_only:
            emit('[DONE] Installed code passed backend --check; server not launched (--install-only).')
            return 0
        rc=_start_backend(root,interpreter)
        # 31 means launch failed *before readiness*, not a later user stop.
        if rc==31:
            raise RuntimeError('Updated backend never became ready (code 31).')
        return rc
    except Exception as exc:
        emit('[STARTUP FAILURE]',type(exc).__name__,str(exc)[:1800])
        if receipt.get('changed'):
            emit('[ROLLBACK] New installation failed startup. Restoring the previous verified code.')
            try: rollback_install(receipt)
            except Exception as rollback_error:
                emit('[URGENT] Automatic rollback failed:',str(rollback_error))
                emit('[BACKUP]',receipt.get('backup'))
                return 78
        else:
            emit('[NOTICE] No files were changed this run; no rollback needed.')
        emit('[NEXT] Existing engineering files remain unchanged. See backend_latest.log.')
        return 32

if __name__=='__main__':
    try: sys.exit(main(sys.argv))
    except Exception:
        details = traceback.format_exc()
        emit('[FATAL] '+details)
        sys.exit(70)
