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
import os
from functools import lru_cache
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NEW_RUNTIME = ("fea_convergence.py", "fea_mesh_series.py", "fea_load_moment.py",
               "fea_compare.py", "fea_history_a03.py", "fea_history_delete_a04.py",
               "fea_field_a06.py", "fea_report_a08.py")
SOURCE_AT_ROOT = frozenset(NEW_RUNTIME)
TOP_LEVEL = ("GeoField_Start.cmd", "GeoField_Repair.cmd", "geofield_port_recovery.py",
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

# Byte-exact source from a previously issued GeoField Windows AutoRepair
# package. Its embedded ZIP was independently unpacked and SHA-256 checked
# against the CMD's embedded integrity constant. These are hashes of the real
# payload source files, NOT arbitrary hashes learned from the user's PC.
# Previously deployed artifact ZIP SHA-256:
# 18f413ad72b29078e38d5565b2f53783643de73a9e8d429b7da41b8bba06bf04
VERIFIED_PREVIOUS_WINDOWS_PACKAGE_SHA256 = "18f413ad72b29078e38d5565b2f53783643de73a9e8d429b7da41b8bba06bf04"
VERIFIED_PREVIOUS_WINDOWS_SOURCE_SHA256 = {
    "GeoField_CAD_Analysis.py": "c3c19306ec4e4f308cd39a0ac05b24faa9c157748ee78dde18e5abd4ab34dd8d",
    "frontend/cad.js": "936641e01a67b21a9c2a2dee3729afc4c891dcbc2fd2534ac1021621928f5f59",
    "frontend/index.html": "012b066ef84eb3568a79dd096e1f8160aa2cb042f55711b3ffdc912ea9b4da84",
    "ml_env_resolver.py": "c6aad7f2a7bf4e8e25b6017e88b152a3f0984318e9a8702f567730cae348237a",
    "ml_r12_bridge.py": "16e90c83972f13925c10c6e6c9b3588402f1b43264daecd4b87f3d873908e8aa",
}


# Verified bytes from actual GitHub Actions *distributed ZIPs*, not from
# unmerged branch source. A+B CI temporarily merges the FEA branch, so the
# ZIP payload hashes do NOT necessarily equal git-show from any branch.
# Artifacts: R3 #12622225719, UI-FOCUS-V1 #12623077621,
# four-menu stage1 #12623735537. Independently downloaded, manifest-checked.
KNOWN_RELEASED_FRONTEND_HASHES = {
    "frontend/cad.js": (
        "7ae70fead4632c7bc3d718e5c2d86d3b5cb9914511de4b3a00d8e856ae548340",
        "be783fe51436b48f3465f2f0e00aba186ed9865cc67635f33d3a0ed9d77a2593",
        "b2053037549b9bb57d6ca04164b87dfa181641cf13f275ae0ee47391fc92e52b",
    ),
    "frontend/index.html": (
        "df1c9957699d72a023415ebe267ff02df522d3a194a89c1346e942f80ca49092",
        "431fcb56b5b062aa0efecfb1bf30129b7e75500ff291a6686da1c863df98f18b",
        "e2492a5cc952e5e5198d434674a6738be7ededef616600f43b7a3ae546c9b99a",
    ),
}

@lru_cache(maxsize=1)
def released_frontend_provenance():
    return (
        ("r3",12622225719,"b9b92f54c3ae2d3f154445249d56b406bf2a15a5f26eed168833142a9e9afc31"),
        ("ui-focus-v1",12623077621,"c6dc73376bc03e519fcc230572a10203be12fb0f015cc928cbbf4993a29d0049"),
        ("four-menu-stage1",12623735537,"2cd9bd6f69cc37168a70a332f6b17be7e91de95c3d000089708e6e42dd342795"),
    )


@lru_cache(maxsize=64)
def trusted_prior_hashes(name):
    """SHA256 from version history reachable through exact reviewed Git commits.

    Unlike local runtime files, the prior Git objects are pinned and reviewable.
    Unknown local source is always refused; this is NOT a forced upgrade.
    """
    source_name = name if name in SOURCE_AT_ROOT else "payload/" + name
    source_path = "src/" + source_name
    commits = set()
    for label, pin in TRUSTED_PRIOR_COMMITS.items():
        try:
            history = subprocess.run(
                ["git","-C",str(ROOT),"log","--format=%H","--max-count=80",
                 pin,"--",source_path],
                capture_output=True,text=True,check=True,timeout=20)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Cannot establish pinned Git history: " + label) from exc
        for commit in history.stdout.splitlines():
            if len(commit)!=40 or any(ch not in "0123456789abcdef" for ch in commit):
                raise RuntimeError("Malformed historical Git SHA: " + name)
            commits.add(commit)
        commits.add(pin)
    found={}
    for commit in sorted(commits):
        try:
            blob = subprocess.run(
                ["git","-C",str(ROOT),"show",commit+":"+source_path],
                capture_output=True,check=False,timeout=20)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Cannot inspect reviewed historical Git source") from exc
        if blob.returncode == 0:
            found[commit] = digest(blob.stdout)
        elif (b"does not exist" in blob.stderr or
              b"exists on disk" in blob.stderr or
              b"unknown revision" in blob.stderr):
            continue
        else:
            raise RuntimeError("Could not verify pinned Git source for " + name)
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
        "approved_previous_windows_package_sha256": VERIFIED_PREVIOUS_WINDOWS_PACKAGE_SHA256,
        "approved_previous_windows_file_sha256": VERIFIED_PREVIOUS_WINDOWS_SOURCE_SHA256,
        "approved_distributed_frontend_artifacts": released_frontend_provenance(),
        "preceding_successful_candidate_sha256":
            previous_distribution()["zip_sha256"] if previous_distribution() else None,
        "required_payload_count": len(files),
        "payload_sha256": {
            name: meta["to"] for name, meta in sorted(files.items())
        },
        "real_calculix_study": "NOT_VERIFIED_BY_PACKAGE_BUILD",
        "actual_user_windows_test": "NOT_VERIFIED_BY_PACKAGE_BUILD",
        "production_release_approved": False,
    }



def _strict_hash(value):
    return (isinstance(value,str) and len(value)==64 and
            all(char in "0123456789abcdef" for char in value))


@lru_cache(maxsize=1)
def previous_distribution():
    """Read real prior GitHub Actions ZIP from CI, not an installed user file.

    CI fetches a successful, GitHub-SHA256-verified artifact from THIS
    repository. Inherited accepted hashes preserve skipped-version upgrades.
    Missing CI artifact is an error when the environment requires lineage.
    """
    location = os.environ.get("GF_PRIOR_CANDIDATE_ZIP")
    if not location:
        if os.environ.get("GF_REQUIRE_PRIOR_CANDIDATE") == "1":
            raise RuntimeError("CI release lineage is required, but prior artifact is missing")
        return None
    package = Path(location)
    if not package.is_file() or package.is_symlink():
        raise RuntimeError("Missing preceding verified GeoField candidate ZIP")
    bytes_sha = digest(package.read_bytes())
    expected = os.environ.get("GF_PRIOR_CANDIDATE_SHA256")
    if not expected or not _strict_hash(expected) or expected != bytes_sha:
        raise RuntimeError("Prior GitHub artifact ZIP SHA256 was not authenticated")
    from installer import ALLOWED_TARGETS
    with zipfile.ZipFile(package) as z:
        listing = z.infolist()
        paths = [info.filename for info in listing]
        if len(paths) != len(set(paths)) or any(
                info.is_dir() or
                ((info.external_attr >> 16) & 0o170000) == 0o120000 or
                ".." in Path(info.filename).parts or
                info.filename.startswith(("/", "\\\\")) for info in listing):
            raise RuntimeError("Untrusted prior ZIP paths")
        old = json.loads(z.read("manifest.json"))
        if (old.get("runtime_id") != "8a9ac53a821a0eb5" or
                set(old.get("files",{})) not in (
                    ALLOWED_TARGETS,
                    ALLOWED_TARGETS - {"fea_field_a06.py", "fea_report_a08.py"},
                    ALLOWED_TARGETS - {"fea_compare.py", "fea_history_a03.py",
                                       "fea_history_delete_a04.py",
                                       "fea_field_a06.py", "fea_report_a08.py"})):
            raise RuntimeError("Unrecognized preceding GeoField candidate")
        lock = json.loads(z.read("CANDIDATE_SOURCE_LOCK.json"))
        if (lock.get("schema") != "geofield-ab-source-lock-v1" or
                lock.get("required_payload_count") != len(old["files"])):
            raise RuntimeError("Prior candidate has no verified source-lock provenance")
        history = {}
        for name,meta in old["files"].items():
            data = z.read("payload/"+name)
            if digest(data) != meta.get("to") or len(data) != meta.get("bytes"):
                raise RuntimeError("Prior candidate payload verification failed: "+name)
            if lock.get("payload_sha256",{}).get(name) != meta["to"]:
                raise RuntimeError("Prior source lock mismatch: "+name)
            candidate = [meta["to"],meta.get("from"),*(meta.get("compatible_from") or [])]
            if any(not _strict_hash(v) for v in candidate if v is not None):
                raise RuntimeError("Malformed prior approved source hash: "+name)
            history[name] = {value for value in candidate if value is not None}
    return {"zip_sha256":bytes_sha,"hashes":history}


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
    if names != ALLOWED_TARGETS or len(names) != 22:
        raise RuntimeError("Installer targets do not match the 22 required package files")
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
            # Allow updating the exact bytes from the previously delivered
            # Windows AutoRepair release, never an unverified local edit.
            known_windows_release = VERIFIED_PREVIOUS_WINDOWS_SOURCE_SHA256.get(name)
            if (known_windows_release and known_windows_release != digest(data) and
                    known_windows_release not in compatible):
                compatible.append(known_windows_release)
            meta["compatible_from"] = compatible
        elif name in ("fea_load_moment.py", "fea_compare.py",
                           "fea_history_a03.py", "fea_history_delete_a04.py",
                           "fea_field_a06.py", "fea_report_a08.py"):
            # Older 17-file releases did not include these source modules.
            # Only absent files are freely added; existing unknown code is blocked.
            meta = {"allow_missing_from": True,
                    "compatible_from": list(dict.fromkeys(trusted_prior_hashes(name).values()))}
            if name == "fea_compare.py":
                # A legacy runtime may have this module outside the updater.
                # Approve only its exact public main version, not unknown edits.
                meta["from"] = digest(original_main(name))
        else:
            # Upgrading preexisting, unbundled A modules is allowed only from
            # the exact original main or known pinned A/B branch snapshots.
            old_path = original_main(name)
            meta = {"from": digest(old_path),
                    "compatible_from": list(dict.fromkeys(trusted_prior_hashes(name).values()))}
        # A+B scratch-merged distribution bytes can differ from committed
        # sources. Preserve known real ZIP hashes and transitive history from
        # the most recent authenticated successful CI-distributed ZIP.
        extra = list(KNOWN_RELEASED_FRONTEND_HASHES.get(name,()))
        prior = previous_distribution()
        if prior:
            extra.extend(sorted(prior["hashes"].get(name,())))
        approved = list(meta.get("compatible_from") or [])
        for exact in extra:
            if not _strict_hash(exact):
                raise RuntimeError("Invalid released source digest: "+name)
            if exact not in approved and exact not in (meta.get("from"),digest(data)):
                approved.append(exact)
        meta["compatible_from"] = approved
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
        "5. Run GeoField_Start.cmd. It verifies the package, checks local dependencies,\n"
        "   offers a one-time backed-up code migration only when approved,\n"
        "   and starts the real 127.0.0.1:8600 backend. Keep its CMD OPEN.\n"
        "6. If source mismatch is found, read the SHA backup details before\n"
        "   entering MIGRATE CODE. Optional GeoField_Repair.cmd is for explicit repair.\n"
        "7. GeoField_Acceptance_Check.cmd is READ-ONLY, NOT THE LAUNCHER.\n"
        "   Run it only AFTER GeoField_Start.cmd is running, STEP is loaded\n"
        "   and a real FEA run is complete. Offline/not_verified is not a solver failure.\n"
        "   DO NOT run a CMD from Bandizip, 7-Zip, WinRAR or a ZIP preview.\n"
        "\n"
        "Requires an EXISTING compatible GeoField Windows runtime. No full EXE.\n"
        "Will not download dependencies. Preserve your original engineering files.\n"
        "Only a code/source-tested update candidate; real CalculiX/3D unverified.\n"
    )
    (directory / "START_HERE_ONE_EXTRACT.txt").write_text(guide, encoding="utf-8")
    expected["START_HERE_ONE_EXTRACT.txt"] = digest(
        (directory / "START_HERE_ONE_EXTRACT.txt").read_bytes())
    (directory / "CANDIDATE_NOT_FINAL.txt").write_text(
        "A+B integration test candidate ONLY. Not approved for production deployment.\n"
        "No actual user Windows CAD, CalculiX, 3-mesh, GPU or FRD end-to-end test passed.\n"
        "Original engineering data must be backed up before final end-to-end acceptance.\n",
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
        if len(m["files"])!=22:raise RuntimeError("Unexpected file count")
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
