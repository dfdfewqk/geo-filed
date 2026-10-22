# -*- coding: utf-8 -*-
"""Safely identify an older GeoField-owned Windows port 8600 listener.

Only an exact local GeoField Python backend, confirmed both by its read-only
HTTP identity and the Windows TCP owner/command line, can be stopped.
No broad taskkill, process name kill, port scanning, AV bypass, or deletion.
"""
from __future__ import annotations
import json
import os
import ntpath
from pathlib import Path
import re
import subprocess
import urllib.request

PORT = 8600
PHASE = 'integrated-cad-geometry-brepmfr-diagnostic-fea-bridge'


def _powershell(script: str, timeout: int = 15, env=None) -> str:
    creation = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    task = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                          **creation, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          timeout=timeout, env=env)
    if task.returncode:
        raise RuntimeError('Windows listener inspection failed (exit %d): %s' %
                           (task.returncode, (task.stderr or task.stdout)[-400:]))
    return task.stdout.strip()


# No process is stopped by this script. It only reads the TCP owner and CIM data.
OWNER_QUERY = r'''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$conns = @(Get-NetTCPConnection -State Listen -LocalPort 8600 -ErrorAction Stop |
  Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::') })
if ($conns.Count -ne 1) { throw ('Expected one local listener, found ' + $conns.Count) }
$ownerId = [int]$conns[0].OwningProcess
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ownerId" -ErrorAction Stop
if ($null -eq $proc) { throw 'Listener process disappeared' }
$children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$ownerId" -ErrorAction Stop |
    Select-Object -ExpandProperty ProcessId)
[pscustomobject]@{
 pid=$ownerId; name=$proc.Name; executable=$proc.ExecutablePath;
 commandline=$proc.CommandLine; created=$proc.CreationDate.ToString('o');
 children=@($children)
} | ConvertTo-Json -Depth 3 -Compress
'''

# Revalidate the port owner, process creation time and command before stopping.
# Stop-Process targets that one PID only, without -Force or -Recurse.
STOP_VERIFIED = r'''[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$id = [int]$env:GF_PORT_OWNER_ID
$expected = $env:GF_EXPECTED_GEOFIELD_SCRIPT
$created = $env:GF_PORT_OWNER_CREATED
$conn = @(Get-NetTCPConnection -State Listen -LocalPort 8600 -ErrorAction Stop |
    Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::1','::') })
if ($conn.Count -ne 1 -or $conn[0].OwningProcess -ne $id) { throw 'Listener owner changed' }
$p = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction Stop
if ($null -eq $p -or $p.CreationDate.ToString('o') -ne $created -or
    $p.Name -notin @('python.exe','pythonw.exe','python3.exe') -or
    $p.CommandLine.IndexOf($expected, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) { throw 'Process identity changed' }
$children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" -ErrorAction Stop)
if ($children.Count -gt 0) { throw 'Backend has child processes; possible active calculation' }
Stop-Process -Id $id -ErrorAction Stop
Write-Output ('STOPPED_VERIFIED_GEOFIELD_PID=' + $id)
'''


def geo_http_identity(port=PORT):
    """Read-only local identity; accepting unrelated processes is forbidden."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:%d/api/status' % port, timeout=2.5) as reply:
            if reply.status != 200:
                return False
            body = json.loads(reply.read(65536))
        return (isinstance(body, dict) and body.get('ok') is True and
                body.get('phase') == PHASE and
                body.get('version') == 'R20-core-stabilization' and
                re.fullmatch(r'[0-9a-f]{32}', str(body.get('server_instance') or '')) is not None and
                # Old backends without explicit activity evidence are not safe
                # to terminate automatically. They must exit normally instead.
                type(body.get('active_work_count')) is int and
                body['active_work_count'] == 0 and
                body.get('safe_to_update') is True)
    except (OSError, ValueError, TypeError, TimeoutError):
        return False


def verified_windows_owner(owner: dict, expected_script: Path) -> bool:
    if not isinstance(owner, dict):
        return False
    if type(owner.get('pid')) is not int or owner['pid'] < 4:
        return False
    if str(owner.get('name') or '').casefold() not in {'python.exe', 'pythonw.exe', 'python3.exe'}:
        return False
    cmd = str(owner.get('commandline') or '')
    actual_exe = str(owner.get('executable') or '')
    created = str(owner.get('created') or '')
    if not actual_exe or not cmd or not created or not ntpath.basename(actual_exe).lower().startswith('python'):
        return False
    if not re.search(r'(?:^|\s)(?:"[^"]+"|\S*python(?:w|3)?\.exe)(?=\s)', cmd, re.I):
        # Some Windows launcher invocations include a bare python.exe first.
        if not cmd.lower().startswith(('python.exe ', 'pythonw.exe ', 'python3.exe ')):
            return False
    if re.search(r'(?:^|\s)-(?:c|m)(?:\s|$)', cmd, re.I):
        return False
    expected = str(expected_script).replace('/', '\\')
    # Accept a precisely delimited script argument, never a partial path or filename.
    expression = r'(?:^|[\s"])' + re.escape(expected) + r'(?=\s|"|$)'
    if not re.search(expression, cmd.replace('/', '\\'), re.I):
        return False
    if not re.search(r'(?<!\w)--port\s+8600(?=\s|$)', cmd, re.I):
        return False
    kids = owner.get('children')
    if not isinstance(kids, list) or kids:
        return False
    return True


def stop_verified_old_geofield(root: Path, emit=print, *, inspect=_powershell, identity=geo_http_identity) -> bool:
    """Best-effort automatic restart, only for a verifiably owned backend.

    False means uncertain / blocked; caller must preserve files and stop.
    """
    if os.name != 'nt':
        emit('[PORT] Auto-release requires Windows; not attempted.')
        return False
    try:
        if not identity(PORT):
            emit('[PORT] Listener is not a verified GeoField backend; it will not be stopped.')
            return False
        owner = json.loads(inspect(OWNER_QUERY))
        expected = Path(root) / 'GeoField_CAD_Analysis.py'
        if not verified_windows_owner(owner, expected):
            emit('[PORT] Could not prove idle GeoField ownership; no process was stopped.')
            return False
        env = os.environ.copy()
        env.update(GF_PORT_OWNER_ID=str(owner['pid']), GF_PORT_OWNER_CREATED=owner['created'],
                   GF_EXPECTED_GEOFIELD_SCRIPT=str(expected))
        # A second read-only identity check closes the interval before the stop.
        if not identity(PORT):
            emit('[PORT] GeoField identity changed; no stop attempted.')
            return False
        result = inspect(STOP_VERIFIED, timeout=15, env=env)
        if 'STOPPED_VERIFIED_GEOFIELD_PID=%d' % owner['pid'] not in result:
            emit('[PORT] Stop was not confirmed; refusing to install while port is occupied.')
            return False
        emit('[PORT] Previous verified GeoField backend closed (PID %d).' % owner['pid'])
        return True
    except (OSError, RuntimeError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        emit('[PORT] Automatic release refused:', type(exc).__name__, str(exc)[:300])
        return False
