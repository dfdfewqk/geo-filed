# -*- coding: utf-8 -*-
"""Read-only GeoField local code-version audit, before upgrade/port stop.

No imports or execution of installed modules. Does not inspect STEP,
SQLite, credentials, FRD, ML weights, private files or arbitrary directories.
Hashes only the 17 package-approved code/model payload targets and reports
only fixed relative filenames and SHA-256 digests.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

from installer import ALLOWED_TARGETS


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda:handle.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def assess_compatibility(runtime,manifest):
    """Inspect local source versions; keep unknown code strictly blocked."""
    runtime = Path(runtime)
    files=manifest.get("files")
    if not isinstance(files,dict) or set(files)!=ALLOWED_TARGETS:
        raise ValueError("Unrecognized manifest targets")
    expected_runtime=manifest.get("runtime_id")
    if expected_runtime!="8a9ac53a821a0eb5":
        raise ValueError("Unknown GeoField runtime identity")
    report={
        "schema":"geofield-local-version-compatibility-v1",
        "created_utc":dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "mode":"read_only_sha256",
        "runtime_id":expected_runtime,
        "candidate_file_count":len(files),
        "installed_runtime_present":runtime.is_dir() and not runtime.is_symlink(),
        "safe_to_install":False,
        "blocking_files":[],
        "file_versions":{},
        "user_data_inspected":False,
        "local_code_executed":False,
        "external_network_used":False,
        "note":"No files updated. Unknown source hashes are never silently approved."
    }
    if not report["installed_runtime_present"]:
        report["blocking_files"]=["runtime_root"]
        return report
    for name,meta in sorted(files.items()):
        rel=Path(*name.split("/"))
        target=runtime/rel
        if target.is_symlink() or any(p.is_symlink() for p in target.parents if p!=runtime.parent):
            state="unsafe_link";old=None
        elif not target.is_file():
            state="missing_allowed" if meta.get("allow_missing_from") is True else "missing_blocked"
            old=None
        else:
            try:
                old=file_sha256(target)
                if old==meta.get("to"):
                    state="already_current"
                elif old==meta.get("from") or old in meta.get("compatible_from",[]):
                    state="verified_prior_version"
                else:
                    state="unrecognized_local_source"
            except OSError:
                state="unreadable";old=None
        report["file_versions"][name]={"status":state,"installed_sha256":old}
        if state not in ("already_current","verified_prior_version","missing_allowed"):
            report["blocking_files"].append(name)
    report["safe_to_install"]=not report["blocking_files"]
    return report


def write_compatibility_report(report,destination):
    """Write only fixed-file inventory to a user diagnostics location."""
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2,
                                      sort_keys=True)+"\n",encoding="utf-8")
    return destination
