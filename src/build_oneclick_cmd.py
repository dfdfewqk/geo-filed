"""Make ONE self-extracting CMD from the verified Stage5 Windows update candidate.

The CMD embeds the entire verified runtime update ZIP. It runs directly when
downloaded or double-clicked from an archive utility; it does not need a
separately extracted payload directory. This is an update for an EXISTING
GeoField runtime, not a new stand-alone CAD/FEA distribution.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import textwrap
import zipfile

from installer import ALLOWED_TARGETS

MARKER = "::GEOFIELD_STAGE5_EMBEDDED_ZIP_START::"
REQUIRED = frozenset({
    "GeoField_Start.cmd", "bootstrap.py", "installer.py",
    "manifest.json", "verify_package.py", "runtime_preflight.py",
    "geofield_port_recovery.py",
})
LIMIT = 8 * 1024 * 1024


def verify_candidate(raw):
    if len(raw) > LIMIT:
        raise ValueError("Bundle too large for Windows single-CMD launch")
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)):
            raise ValueError("Repeated paths in the update ZIP")
        for item in members:
            p = PurePosixPath(item.filename)
            if (p.is_absolute() or not p.parts or
                any(part in ("..", ".") or ":" in part or "\\" in part for part in p.parts) or
                (item.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError("Unsafe ZIP member: " + item.filename)
        if not REQUIRED.issubset(names):
            raise ValueError("Update ZIP is incomplete or double wrapped: " +
                             repr(sorted(REQUIRED - set(names))))
        manifest = json.loads(archive.read("manifest.json"))
        file_map = manifest.get("files")
        if (manifest.get("runtime_id") != "8a9ac53a821a0eb5" or
            not isinstance(file_map, dict) or
            set(file_map) != ALLOWED_TARGETS or len(file_map) != 19):
            raise ValueError("Unsupported GeoField update manifest")
        for name, info in file_map.items():
            location = "payload/" + name
            if location not in names or not isinstance(info, dict):
                raise ValueError("Missing SHA-locked payload: " + location)
            data = archive.read(location)
            if (hashlib.sha256(data).hexdigest() != info.get("to") or
                len(data) != info.get("bytes")):
                raise ValueError("Unverified payload: " + location)
        expected = REQUIRED | {"CANDIDATE_NOT_FINAL.txt", "CANDIDATE_SOURCE_LOCK.json"} | {
            "payload/" + name for name in file_map}
        if set(names) != expected:
            raise ValueError("Unexpected ZIP inventory: " + repr(sorted(set(names) ^ expected)))
        return manifest


def build(archive, output):
    archive = Path(archive)
    output = Path(output)
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing one-click CMD")
    raw = archive.read_bytes()
    verify_candidate(raw)
    checksum = hashlib.sha256(raw).hexdigest()
    # No generated PowerShell scripts or user-space policy changes are needed.
    # The Windows PowerShell one-liner only extracts the exact SHA-256 bundle.
    ps = (
        "$ErrorActionPreference='Stop';"
        "$txt=[IO.File]::ReadAllText($env:GF_SFX_SOURCE,[Text.Encoding]::UTF8);"
        "$tag='" + MARKER + "';"
        "$pos=$txt.LastIndexOf($tag);"
        "if($pos -lt 0){throw 'Embedded GeoField payload missing'};"
        "$b64=$txt.Substring($pos+$tag.Length) -replace '[^A-Za-z0-9+/=]','';"
        "$bin=[Convert]::FromBase64String($b64);"
        "$h=[Security.Cryptography.SHA256]::Create();"
        "$actual=[BitConverter]::ToString($h.ComputeHash($bin)).Replace('-','').ToLowerInvariant();"
        "if($actual -ne $env:GF_SFX_SHA){throw 'Corrupt GeoField download: ZIP SHA256 mismatch'};"
        "$zip=Join-Path $env:GF_SFX_DIR 'package.zip';"
        "$dest=Join-Path $env:GF_SFX_DIR 'bundle';"
        "[IO.File]::WriteAllBytes($zip,$bin);"
        "Add-Type -AssemblyName System.IO.Compression.FileSystem;"
        "[IO.Compression.ZipFile]::ExtractToDirectory($zip,$dest);"
        "foreach($name in @('GeoField_Start.cmd','bootstrap.py','installer.py','manifest.json','verify_package.py'))"
        "{if(-not (Test-Path -LiteralPath (Join-Path $dest $name) -PathType Leaf))"
        "{throw ('Package file missing: '+$name)}};"
        "Write-Output '[OK] All files extracted from embedded SHA-verified package'"
    )
    lines = [
        "@echo off",
        "setlocal EnableExtensions DisableDelayedExpansion",
        "chcp 65001 >nul 2>&1",
        "title GeoField Stage5 - One Click Windows Runtime Update",
        "rem This file embeds the entire update ZIP; do NOT unzip it separately.",
        "rem This is an update to an existing GeoFieldCAD Windows installation.",
        'if not defined TEMP goto :no_temp',
        'if not defined LOCALAPPDATA goto :no_local',
        'set "GF_SFX_SOURCE=%~f0"',
        'set "GF_SFX_SHA=' + checksum + '"',
        'set "GF_SFX_DIR=%TEMP%\\GeoFieldStage5_%RANDOM%_%RANDOM%_%RANDOM%"',
        'if exist "%GF_SFX_DIR%" goto :collision',
        'mkdir "%GF_SFX_DIR%" || goto :fail',
        'echo [1/2] Extract embedded verified GeoField update automatically...',
        'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ^',
        ' "' + ps + '"',
        'if errorlevel 1 goto :extract_failed',
        'echo [2/2] Verify the package and start existing GeoField...',
        'if /I "%~1"=="--self-test" (',
        '  call "%GF_SFX_DIR%\\bundle\\GeoField_Start.cmd" --verify-only',
        ') else (',
        '  rem The one-click UPDATE explicitly requests guarded recovery of earlier GeoField UI sources.',
        '  call "%GF_SFX_DIR%\\bundle\\GeoField_Start.cmd" --repair-managed-code %*',
        ')',
        'set "GF_SFX_RESULT=%ERRORLEVEL%"',
        'if not "%GF_SFX_RESULT%"=="0" echo [ERROR] GeoField update/start failed; see diagnostics above.',
        'goto :cleanup',
        ':extract_failed',
        'echo [ERROR] Self-extraction or package integrity failed. Existing GeoField not modified.',
        'set "GF_SFX_RESULT=40"',
        'goto :cleanup',
        ':collision',
        'echo [ERROR] Temporary folder conflict, please run again.',
        'set "GF_SFX_RESULT=41"',
        'goto :end',
        ':no_temp',
        'echo [ERROR] Windows TEMP path unavailable.',
        'set "GF_SFX_RESULT=42"',
        'goto :end',
        ':no_local',
        'echo [ERROR] Windows LOCALAPPDATA path unavailable.',
        'set "GF_SFX_RESULT=43"',
        'goto :end',
        ':fail',
        'echo [ERROR] Cannot create a temporary extraction folder.',
        'set "GF_SFX_RESULT=44"',
        'goto :end',
        ':cleanup',
        'rem Delete only the unique temporary folder created by this invocation.',
        'if exist "%GF_SFX_DIR%\\bundle\\GeoField_Start.cmd" (',
        '  if exist "%GF_SFX_DIR%\\package.zip" rd /s /q "%GF_SFX_DIR%" >nul 2>&1',
        ')',
        ':end',
        'exit /b %GF_SFX_RESULT%',
        MARKER,
    ]
    encoded = base64.b64encode(raw).decode("ascii")
    # Prefixed comment lines remain inert in cmd.exe; PowerShell removes "::".
    lines.extend("::" + line for line in textwrap.wrap(encoded, 160))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    return checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    digest = build(args.archive, args.output)
    print("[ONE_CLICK]", args.output, "bytes=", args.output.stat().st_size)
    print("[EMBEDDED_ZIP_SHA256]", digest)
    print("[LIMIT] Requires an existing GeoFieldCAD runtime; not a new installer")


if __name__ == "__main__":
    main()
