"""B02 fail-closed filesystem contract for a single real FEA solver run.

Does not import Gmsh/CCX, execute a solver, change any existing file or
invent STEP/INP/STA/FRD evidence. Directories and files are checked before
running the solver; old output is never deleted to make tests pass.
"""
from __future__ import annotations

import ast
import re
import stat
from pathlib import Path

RUN = re.compile(r"^[0-9a-f]{32}$")
# Output from an earlier calculation must never look like output of this run.
SOLVER_OUTPUTS = frozenset({
    "geofield_case.inp", "geofield_case.sta", "geofield_case.frd",
    "geofield_case.dat", "geofield_case.cvg",
    "ccx_execution.log", "geofield_fea_surface_field.json",
    # case.json is a staged INPUT for the standalone actual C3D10 runner,
    # not CalculiX output. HTTP still refuses ANY populated run directory
    # in validate_new_run(), including one containing case.json.
    "result.json", "worker_result.json", "worker.log",
    "error.log",
})


def _safe_directory(path):
    path = Path(path)
    for node in (path, *path.parents):
        if node.is_symlink():
            raise ValueError("FEA 작업 경로에 심볼릭 링크가 있습니다.")
    if path.exists() and not path.is_dir():
        raise ValueError("FEA 계산 작업 디렉터리가 아닙니다.")
    return path


def validate_new_run(jobs_dir, run_id):
    """No stage may reuse a previously populated run folder."""
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
        raise ValueError("FEA 실행 ID 형식 오류")
    root = _safe_directory(jobs_dir)
    parent = _safe_directory(root / "fea_runs")
    run = _safe_directory(parent / run_id)
    if run.exists():
        try:
            if next(run.iterdir(), None) is not None:
                raise ValueError("같은 FEA 실행 ID의 작업 파일이 이미 존재하여 재사용을 차단합니다.")
        except OSError as exc:
            raise ValueError("이전 FEA 실행 폴더를 안전하게 검사할 수 없습니다.") from exc
    return run


def validate_clean_solver_artifacts(workdir):
    """Reject stale results even when the real worker is invoked separately.

    A worker may legitimately stage worker_case.json and worker_model.json;
    those are not solver outputs. All actual solver artifacts must start absent.
    """
    folder = _safe_directory(workdir)
    if not folder.exists():
        return True
    try:
        for name in SOLVER_OUTPUTS:
            item = folder / name
            if item.is_symlink() or item.exists():
                raise ValueError("이전 FEA 솔버 파일의 재사용을 차단합니다: " + name)
    except OSError as exc:
        raise ValueError("기존 FEA 계산 파일을 안전하게 확인할 수 없습니다.") from exc
    return True


def owned_temporary_step(jobs_dir, run_id, candidate):
    """Only HTTP-created run-UUID temporary STEP bytes may be unlinked.

    Never infer ownership from .step extension, a filename substring, or
    location inside the user's original CAD directories.
    """
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
        return False
    try:
        root = _safe_directory(jobs_dir)
        path = Path(candidate)
        expected = root / (run_id + ".fea_input.step")
        if path != expected or path.is_symlink() or not path.is_file():
            return False
        _safe_directory(path.parent)
        return stat.S_ISREG(path.stat().st_mode)
    except (ValueError, OSError, TypeError):
        return False


def existing_worker_is_safe(root):
    """Read-only installed private worker source check, NOT an execution test."""
    try:
        directory = _safe_directory(root)
        worker = directory / "fea_engine_worker.py"
        if worker.is_symlink() or not worker.is_file():
            return False
        state = worker.stat()
        if not stat.S_ISREG(state.st_mode) or not (0 < state.st_size <= 2_000_000):
            return False
        source = worker.read_bytes()
        if len(source) != state.st_size or b"\x00" in source:
            return False
        ast.parse(source.decode("utf-8-sig"), filename="fea_engine_worker.py")
        return True
    except (OSError, UnicodeError, SyntaxError, ValueError, TypeError):
        return False
