# -*- coding: utf-8 -*-
"""Build a verifiable A+B integration *candidate* from a scratch merged checkout.

Never modify src/manifest.json, src/verify_package.py, source data or the user's
installed GeoField. CI calls this only AFTER merging A into its temporary checkout.
Real Gmsh/CalculiX, 3D graphics and private engineering data are not tested here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NEW_RUNTIME = ("fea_convergence.py", "fea_mesh_series.py", "fea_load_moment.py")
SOURCE_AT_ROOT = frozenset(NEW_RUNTIME)
TOP_LEVEL = ("GeoField_Start.cmd", "geofield_port_recovery.py",
             "bootstrap.py", "installer.py", "runtime_preflight.py",
             "GeoField_Acceptance_Check.cmd", "acceptance_probe.py")
HISTORICAL_BASE = "refs/remotes/origin/main"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def original_main(path):
    """Use EXACT GitHub main bytes for permitted upgrades, never guess hashes."""
    result = subprocess.run(["git", "-C", str(ROOT), "show", HISTORICAL_BASE + ":src/" + path],
                            capture_output=True, check=True)
    return result.stdout


def _revision(ref):
    """Git hash of a source revision; fail if an upstream ref is missing."""
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--verify",
                             ref + "^{commit}"],
                            capture_output=True, text=True, check=True)
    rev = result.stdout.strip()
    if len(rev) != 40 or any(c not in "0123456789abcdef" for c in rev):
        raise RuntimeError("Invalid full Git source commit ID: " + ref)
    return rev


def source_lock(files):
    """A+B ancestry + exact runtime payload bytes, without a release claim."""
    return {
        "schema": "geofield-ab-source-lock-v1",
        "status": "TEST_CANDIDATE_NOT_FINAL",
        "source_revisions": {
            "b_branch_checkout": _revision("HEAD"),
            "a_fea_branch": _revision("refs/remotes/origin/work/fea-validation"),
            "historical_main_baseline": _revision(HISTORICAL_BASE),
        },
        "merge_mode": "scratch_checkout_uncommitted_merge_no_push",
        "required_payload_count": len(files),
        "payload_sha256": {
            name: meta["to"] for name, meta in sorted(files.items())
        },
        "real_calculix_study": "NOT_VERIFIED_BY_PACKAGE_BUILD",
        "actual_user_windows_test": "NOT_VERIFIED_BY_PACKAGE_BUILD",
        "production_release_approved": False,
    }


def build(directory):
    """Write isolated package tree to a new empty directory, return manifest."""
    from installer import ALLOWED_TARGETS, DirectoryBundle, verify_bundle
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Refusing to overwrite existing candidate directory")
    directory.mkdir(parents=True, exist_ok=True)
    previous = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    old_files = previous["files"]
    names = set(old_files) | set(NEW_RUNTIME)
    if names != ALLOWED_TARGETS or len(names) != 17:
        raise RuntimeError("Installer targets do not match the 17 required package files")
    manifest = dict(previous)
    manifest["release"] = ("A+B engineering integration candidate; Windows CAD/FEA/3D "
                           "end-to-end and independent real three-run solver evidence NOT verified")
    manifest["files"] = {}
    for name in sorted(names):
        source = ROOT / (name if name in SOURCE_AT_ROOT else "payload/" + name)
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("Missing trusted integration source: " + name)
        data = source.read_bytes()
        output = directory / "payload" / name
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        if name in old_files:
            meta = dict(old_files[name])
            # R12.13 is an individually verified upgrade base. Preserve its hash
            # as an accepted previous VERSION, without trusting arbitrary files.
            if meta.get("to") != digest(data):
                compatible = list(meta.get("compatible_from") or [])
                if meta["to"] not in compatible:
                    compatible.append(meta["to"])
                meta["compatible_from"] = compatible
        elif name == "fea_load_moment.py":
            # Newly added module: install only if it does not exist already.
            meta = {"allow_missing_from": True}
        else:
            # Upgrading preexisting, unbundled A modules is allowed only from
            # the exact version committed on origin/main.
            old_path = original_main(name)
            meta = {"from": digest(old_path)}
        meta["to"] = digest(data)
        meta["bytes"] = len(data)
        manifest["files"][name] = meta
    manifest_data = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    (directory / "manifest.json").write_bytes(manifest_data)
    lock = source_lock(manifest["files"])
    (directory / "CANDIDATE_SOURCE_LOCK.json").write_text(
        json.dumps(lock, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for name in TOP_LEVEL:
        source = ROOT / name
        if not source.is_file() or source.is_symlink():
            raise RuntimeError("Missing entrypoint: " + name)
        shutil.copy2(source, directory / name)
    expected = {name: digest((directory / name).read_bytes())
                for name in (*TOP_LEVEL[1:], "manifest.json")}
    expected.update({"payload/" + name: digest((directory / "payload" / name).read_bytes())
                     for name in sorted(names)})
    # The root entrypoint is also SHA checked. No recursive/self-hash problem:
    # verify_package.py is generated last and never hashes itself.
    expected[TOP_LEVEL[0]] = digest((directory / TOP_LEVEL[0]).read_bytes())
    expected["CANDIDATE_SOURCE_LOCK.json"] = digest(
        (directory / "CANDIDATE_SOURCE_LOCK.json").read_bytes())
    (directory / "CANDIDATE_NOT_FINAL.txt").write_text(
        "A+B integration test candidate ONLY. Not approved for installation.\\n"
        "No actual user Windows CAD, CalculiX, 3-mesh, GPU or FRD end-to-end test passed.\\n"
        "Original engineering data must be backed up before final end-to-end acceptance.\\n",
        encoding="utf-8")
    expected["CANDIDATE_NOT_FINAL.txt"] = digest(
        (directory / "CANDIDATE_NOT_FINAL.txt").read_bytes())
    verifier = '''# -*- coding: utf-8 -*-
"""SHA-256 integrity proof generated for this exact staging folder."""
import hashlib
import sys
from pathlib import Path
sys.dont_write_bytecode=True  # No unlisted __pycache__ files on re-verification.
BASE=Path(__file__).resolve().parent
EXPECTED=''' + repr(expected) + '''
def main():
    allowed=set(EXPECTED) | {"verify_package.py"}
    discovered=set()
    for p in BASE.rglob("*"):
        if p.is_symlink():
            print("[ERROR] Candidate contains symlink:",p,flush=True)
            return 11
        if p.is_file():
            discovered.add(p.relative_to(BASE).as_posix())
    if discovered!=allowed:
        print("[ERROR] Candidate inventory differs:",
              "extra="+str(sorted(discovered-allowed)),
              "missing="+str(sorted(allowed-discovered)),flush=True)
        return 11
    for name,sha in EXPECTED.items():
        p=BASE/name
        if not p.is_file() or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            print("[ERROR] Unverified candidate file:",name,flush=True)
            return 12
    try:
        from installer import DirectoryBundle,verify_bundle
        m=verify_bundle(DirectoryBundle(BASE))
        if len(m["files"])!=17:raise RuntimeError("Unexpected file count")
        print("[OK] A+B candidate integrity verified:",len(m["files"]),"payload files",flush=True)
        return 0
    except Exception as exc:
        print("[ERROR] Bundle manifest mismatch:",str(exc),flush=True)
        return 13
if __name__=="__main__":sys.exit(main())
'''
    (directory / "verify_package.py").write_text(verifier, encoding="utf-8")
    verify_bundle(DirectoryBundle(directory))
    return manifest


def zip_candidate(folder, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError("Refusing to replace existing ZIP")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=7) as archive:
        for p in sorted(Path(folder).rglob("*")):
            if p.is_file():
                archive.write(p, p.relative_to(folder).as_posix())
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="geofield-integration-") as temporary:
        folder = Path(temporary) / "candidate"
        m = build(folder)
        zipped = zip_candidate(folder, args.output)
        print("[CANDIDATE] " + str(zipped))
        print("[SHA256] " + digest(zipped.read_bytes()))
        print("[PAYLOAD] " + str(len(m["files"])) + " verified runtime files")
        print("[LIMIT] Not a user-validated Windows FEA distribution")


if __name__=="__main__":
    main()
