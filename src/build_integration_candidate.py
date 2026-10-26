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
             "runtime_compatibility.py",
             "GeoField_Acceptance_Check.cmd", "acceptance_probe.py")
HISTORICAL_BASE = "refs/remotes/origin/main"
# Only exact, reviewed Git commits can be admitted as previous versions.
# NEVER use a wildcard, an arbitrary local hash or "force upgrade" for unknown
# user code. Snapshot revisions are recorded in the source lock for review.
TRUSTED_PRIOR_COMMITS = {
    "cad_ml_branch_20261026": "2d58b782c4f9dc1c0bec5685cceb10286f64ab7f",
    "fea_branch_20261026": "e5a419a99c4f36814d4de44d5a69da14553a0e2d",
    "prior_ai_integrated_20261022": "8882ed6be70a1747e8fbd9a13acbf1d341200e61",
}


def trusted_prior_hashes(name):
    """SHA-256s of *actual tracked bytes* at vetted exact commit objects.

    A Git object is skipped if the file was not yet tracked at that revision.
    New unrecognized local modifications remain blocked by the installer.
    """
    source_name = name if name in SOURCE_AT_ROOT else "payload/" + name
    found = {}
    for label, commit in TRUSTED_PRIOR_COMMITS.items():
        try:
            result = subprocess.run(
                ["git", "-C", str(ROOT), "show", commit + ":src/" + source_name],
                capture_output=True, check=False, timeout=15
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Cannot retrieve trusted Git baseline " + label) from exc
        if result.returncode == 0:
            found[label] = digest(result.stdout)
        elif b"does not exist" in result.stderr or b"exists on disk" in result.stderr:
            continue
        else:
            raise RuntimeError("Cannot verify pinned Git baseline " + label)
    return found


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
        "approved_exact_previous_commits": TRUSTED_PRIOR_COMMITS,
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
            # Include only byte-exact old files committed on known GeoField
            # branches. Hashes from a user's untracked files are NOT authorized.
            compatible = list(meta.get("compatible_from") or [])
            for known_sha in trusted_prior_hashes(name).values():
                if known_sha not in compatible and known_sha != meta["to"]:
                    compatible.append(known_sha)
            meta["compatible_from"] = compatible
        elif name == "fea_load_moment.py":
            # New under original release, but may be present from a pinned FEA
            # branch. Still reject unrecognized customized code.
            meta = {"allow_missing_from": True,
                    "compatible_from": list(dict.fromkeys(trusted_prior_hashes(name).values()))}
        else:
            # Upgrading preexisting, unbundled A modules is allowed only from
            # the exact original main or known pinned A/B branch snapshots.
            old_path = original_main(name)
            meta = {"from": digest(old_path),
                    "compatible_from": list(dict.fromkeys(trusted_prior_hashes(name).values()))}
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
    # Important: GitHub Actions artifact downloads already create an outer
    # ZIP. Upload THIS DIRECTORY directly; shipping a second ZIP inside it
    # lets archive viewers launch CMD alone from BNZ temporary directories.
    guide = (
        "GEOFIELD A+B+AI - WINDOWS UPDATE TEST CANDIDATE (NOT FINAL)\n"
        "\n"
        "1. In GitHub Actions Artifacts, download the ONE-EXTRACT candidate ZIP.\n"
        "2. In Windows File Explorer, right-click it -> Extract All ONCE.\n"
        "3. Open that ordinary EXTRACTED FOLDER in Windows File Explorer.\n"
        "4. Check bootstrap.py, installer.py, manifest.json, verify_package.py,\n"
        "   payload/ and GeoField_Start.cmd are in the same directory.\n"
        "5. Double-click GeoField_Start.cmd from Explorer.\n"
        "   DO NOT double-click it from Bandizip, 7-Zip, WinRAR or a ZIP preview.\n"
        "\n"
        "Requires an EXISTING compatible GeoField Windows runtime. No full EXE.\n"
        "Will not download dependencies. Preserve your original engineering files.\n"
        "Only a code/source-tested update candidate; real CalculiX/3D unverified.\n"
    )
    (directory / "START_HERE_ONE_EXTRACT.txt").write_text(guide, encoding="utf-8")
    expected["START_HERE_ONE_EXTRACT.txt"] = digest(
        (directory / "START_HERE_ONE_EXTRACT.txt").read_bytes())
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
