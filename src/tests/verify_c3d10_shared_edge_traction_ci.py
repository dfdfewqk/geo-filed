"""Actual C3D10 shared-support traction A/B experiment (research ONLY).

The CURRENT production solver first runs its unmodified conservative scheme.
On the same deterministic tetrahedral mesh, a separate CalculiX deck replaces
only the *CLOAD cards with the exact consistent straight-Tri6 integration:
each triangle contributes A/3 per midside node, including fixed/load overlap.

Fixed-node force and CalculiX RF conventions are reported distinctly, not
assumed. This script NEVER modifies production fea_solver.py or user CAD/SQLite.
A successful solve does not certify mesh convergence or structural safety.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / "src"), str(ROOT / "src" / "payload"),
    str(ROOT / "src" / "tests" / "fea_ci_dependencies"),
]
from fea_solver import (
    detect_ccx, gmsh_mesh, weighted_surface_force, triangle_area,
    parse_frd_results, run_real_fea, source_face_signatures,
)
from verify_three_mesh_real_ci import reference_case, sha256, relative_percent


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _vector_sum(rows):
    # An iterator/generator can be consumed only once. Materialize vectors
    # before independently summing their three Cartesian components.
    values = [tuple(row) for row in rows]
    if any(len(row) != 3 for row in values):
        raise ValueError("Expected three-component force or moment")
    return [math.fsum(row[k] for row in values) for k in range(3)]


def _moment(nodes, forces):
    return _vector_sum(_cross(nodes[n], v) for n, v in forces.items())


def exact_tri6_surface_loads(nodes, load_tris, force_magnitude, direction):
    """Independent resultant/moment check against the loaded CAD mesh surface.

    Valid for straight, flat six-node triangles, not automatically curved faces
    or element-pressure orientation. Never discard fixed-surface midside nodes.
    """
    if not load_tris or any(len(tri) != 6 for tri in load_tris):
        raise ValueError("Only nonempty straight Tri6 surface meshes are supported")
    midsides = [tri[3:6] for tri in load_tris]
    loads, _quarter_area = weighted_surface_force(
        nodes, midsides, force_magnitude, direction, exclude_nodes=())
    if any(len(set(tri)) != 6 for tri in load_tris):
        raise ValueError("Degenerate six-node face")
    original_area = math.fsum(triangle_area(*(nodes[n] for n in tri[:3])) for tri in load_tris)
    integrated_center = [
        math.fsum(
            triangle_area(*(nodes[n] for n in tri[:3])) *
            sum(nodes[n][k] for n in tri[:3]) / 3
            for tri in load_tris
        ) / original_area for k in range(3)
    ]
    actual_force = _vector_sum(loads.values())
    nominal_force = [force_magnitude*x for x in direction]
    nominal_moment = _cross(integrated_center, nominal_force)
    applied_moment = _moment(nodes, loads)
    if math.dist(actual_force, nominal_force) > max(1e-7, force_magnitude*1e-8):
        raise ValueError("Full consistent Tri6 resultant mismatch")
    if math.dist(applied_moment, nominal_moment) > max(1e-6, force_magnitude*1e-7):
        raise ValueError("Full consistent Tri6 moment mismatch")
    return loads, {
        "source": "straight_Tri6_exact_consistent_nodal_surface_vector_traction",
        "surface_area_mm2": original_area,
        "surface_centroid_mm": integrated_center,
        "applied_resultant_n": actual_force,
        "applied_moment_n_mm": applied_moment,
        "moment_difference_n_mm": math.dist(applied_moment,nominal_moment),
        "uniform_traction_on_straight_tri6_integrated": True,
        "fixed_load_nodes_included": True,
        "curved_CAD_traction_validated": False,
    }


def reconstruct_separate_exact_deck(original, destination, nodes, tets, loads):
    """Copy an independently validated production INP, replacing only CLOAD.

    A deterministic second Gmsh mesh is mandatory: node/tet identity must
    match *exactly* before replacing a single load. Nothing else is rewritten.
    """
    lines = Path(original).read_text(encoding="ascii").splitlines(keepends=True)
    def section(name):
        return [i for i,line in enumerate(lines) if line.strip().upper().split(",")[0] == name]
    start = section("*CLOAD")
    next_section = section("*NODE PRINT")
    elements = [i for i,line in enumerate(lines) if line.strip().upper().startswith("*ELEMENT,")]
    if (len(start) != 1 or len(next_section) != 1 or next_section[0] <= start[0] or
        len(elements) != 1 or "TYPE=C3D10" not in lines[elements[0]].upper() or
        section("*DLOAD")):
        raise ValueError("Unrecognized original C3D10 input deck layout")
    deck_nodes = {}; deck_tets = {}
    mode = None
    for line in lines:
        row = line.strip()
        if row.startswith("*"):
            mode = "nodes" if row == "*NODE" else (
                "tets" if row.startswith("*ELEMENT,") else None)
            continue
        if not row or row.startswith("**"):
            continue
        if mode == "nodes":
            p=[x.strip() for x in row.split(",")]
            if len(p) != 4:
                raise ValueError("Malformed input deck nodes")
            deck_nodes[int(p[0])] = [float(x) for x in p[1:]]
        elif mode == "tets":
            p=[int(x.strip()) for x in row.split(",")]
            if len(p) != 11 or p[0] in deck_tets:
                raise ValueError("Malformed C3D10 deck element")
            deck_tets[p[0]]=p[1:]
    if (set(deck_nodes) != set(nodes) or
        any(math.dist(deck_nodes[n],nodes[n]) > 1e-5 for n in nodes) or
        deck_tets != {eid:list(tet) for eid,tet in tets}):
        raise ValueError("Gmsh original and experimental mesh nodes/elements differ")
    old_segment = lines[start[0]+1:next_section[0]]
    if not old_segment or any(x.lstrip().startswith("*") for x in old_segment):
        raise ValueError("Unexpected original CLOAD section content")
    replacement = [f"{n}, {axis}, {value:.13g}\n"
                   for n,forces in sorted(loads.items())
                   for axis,value in enumerate(forces,1) if abs(value)>1e-15]
    if not replacement:
        raise ValueError("Empty replacement CLOAD")
    Path(destination).write_text(
        "".join(lines[:start[0]+1]+replacement+lines[next_section[0]:]),encoding="ascii")
    original_lines = "".join(lines[:start[0]+1] + lines[next_section[0]:])
    verified_lines = Path(destination).read_text(encoding="ascii").splitlines(keepends=True)
    verified_without_cload = "".join(verified_lines[:start[0]+1]+
        verified_lines[start[0]+1+len(replacement):])
    if verified_without_cload != original_lines:
        raise RuntimeError("Independent deck contains changes outside CLOAD")
    return {"input_sha256":sha256(destination),
            "unchanged_original_sha256":sha256(original),
            "original_nodal_cards":len(old_segment),
            "exact_nodal_cards":len(replacement),
            "only_cload_section_changed":True}


def observed_fixed_rf(dat_path,fixed_nodes):
    """Parse all explicit last-step fixed-node RFs without assuming convention."""
    content=Path(dat_path).read_text(encoding="ascii",errors="strict").splitlines()
    header=re.compile(r"^forces\s*\(\s*fx\s*,\s*fy\s*,\s*fz\s*\)\s+for\s+set\s+GEOFIELD_FIXED\s+and\s+time\s+([+\-\d.EeDd]+)\s*$",re.I)
    row=re.compile(r"^\s*(\d+)\s+([+\-\d.EeDd]+)\s+([+\-\d.EeDd]+)\s+([+\-\d.EeDd]+)\s*$")
    matches=[]
    for i,line in enumerate(content):
        head=header.fullmatch(line.strip())
        if not head:
            continue
        time=float(head.group(1).replace("D","E").replace("d","e"))
        readings={}
        started=False
        for line in content[i+1:]:
            m=row.fullmatch(line)
            if m:
                started=True
                n=int(m.group(1))
                if n in readings or n not in fixed_nodes:
                    raise ValueError("Unknown or duplicate RF node")
                vals=[float(v.replace("D","E").replace("d","e")) for v in m.groups()[1:]]
                if any(not math.isfinite(v) for v in vals):
                    raise ValueError("Non-finite RF")
                readings[n]=vals
            elif started:
                if line.strip():
                    raise ValueError("Corrupted fixed RF table")
                break
            elif line.strip():
                raise ValueError("Malformed RF table")
        matches.append((time,readings))
    if not matches or abs(matches[-1][0]-1)>1e-4 or set(matches[-1][1])!=set(fixed_nodes):
        raise ValueError("Final full fixed RF table missing")
    return matches[-1][1]


def reaction_convention_screen(nodes, fixed_nodes, loads, rf):
    """Report BOTH plausible RF conventions; never silently choose a meaning."""
    fixed_part={n:v for n,v in loads.items() if n in fixed_nodes}
    free_part={n:v for n,v in loads.items() if n not in fixed_nodes}
    rf_force=_vector_sum(rf.values())
    rf_moment=_moment(nodes,rf)
    def residual(forces):
        f=_vector_sum(forces.values())
        m=_moment(nodes,forces)
        return (math.dist(_vector_sum((f,rf_force)),(0.,0.,0.)),
                math.dist(_vector_sum((m,rf_moment)),(0.,0.,0.)))
    full_force,full_moment=residual(loads)
    free_force,free_moment=residual(free_part)
    return {
        "fixed_surface_loaded_nodes":len(fixed_part),
        "fixed_surface_external_force_n":_vector_sum(fixed_part.values()) if fixed_part else [0.,0.,0.],
        "reported_RF_sum_n":rf_force,
        "all_CLOAD_plus_printed_RF_force_residual_n":full_force,
        "all_CLOAD_plus_printed_RF_moment_residual_n_mm":full_moment,
        "free_CLOAD_plus_printed_RF_force_residual_n":free_force,
        "free_CLOAD_plus_printed_RF_moment_residual_n_mm":free_moment,
        "pure_support_reaction_verified":False,
        "note":"Printed RF on loaded fixed nodes may include/omit external loads. Both residual conventions shown. No engineering balance certification inferred.",
    }


def run():
    base = ROOT / "_fea_shared_edge_traction_evidence"
    base.mkdir(exist_ok=True)
    step, physics, model = reference_case(ROOT, sha256(ROOT/"src"/"payload"/"fea_solver.py"))
    physics.pop("solver_sha256")
    rows=[]
    for size in (3.,2.25,1.7):
        case=copy.deepcopy(physics)
        case.update(schema="geofield-fea-case-v1",
                    status="configuration_prepared_solver_not_connected",
                    mesh_request={"target_element_size_mm":size,"element_type":"C3D10"})
        case["case_sha256"]=hashlib.sha256(
            json.dumps(case,sort_keys=True).encode()).hexdigest()
        folder=base/str(size).replace(".","_")
        original=folder/"production_unmodified";original.mkdir(parents=True,exist_ok=True)
        corrected=folder/"research_full_tri6";corrected.mkdir(parents=True,exist_ok=True)
        production=run_real_fea(step,case,model,original)
        if production.get("mesh",{}).get("element_type")!="C3D10":
            raise RuntimeError("Production baseline not C3D10")
        nodes,tets,surfaces,_ = gmsh_mesh(
            step,source_face_signatures(model),
            case["boundary_conditions"]["fixed_face_ids"],
            case["boundary_conditions"]["load_face_ids"],size,"C3D10")
        fixed={n for fid in case["boundary_conditions"]["fixed_face_ids"]
               for tri in surfaces[fid] for n in tri}
        loaded=[tri for fid in case["boundary_conditions"]["load_face_ids"] for tri in surfaces[fid]]
        forces,audit=exact_tri6_surface_loads(
            nodes,loaded,case["boundary_conditions"]["total_force_n"],
            case["boundary_conditions"]["force_direction_unit"])
        if not (set(forces)&fixed):
            raise ValueError("Study must have a shared fixed/loaded midside boundary")
        deck=corrected/"full_tri6.inp"
        deck_audit=reconstruct_separate_exact_deck(
            original/"geofield_case.inp",deck,nodes,tets,forces)
        with (corrected/"full_traction_manifest.json").open("w",encoding="utf8") as f:
            json.dump({"case_sha256":case["case_sha256"],"cad_sha256":case["cad_sha256"],
                       "audit":audit,"deck":deck_audit},f,indent=2)
        exe=detect_ccx()
        if not exe:
            raise RuntimeError("CalculiX ccx missing, not a mock")
        proc=subprocess.run([exe,"-i","full_tri6"],cwd=corrected,
                            capture_output=True,timeout=240,check=False)
        (corrected/"ccx.log").write_text(
            "exit code: "+str(proc.returncode)+"\n"+
            proc.stdout.decode("utf8","replace")[-12000:]+"\n"+
            proc.stderr.decode("utf8","replace")[-8000:],encoding="utf8")
        if proc.returncode:
            raise RuntimeError("Experimental full Tri6 CalculiX failed; inspect raw artifacts")
        for ext in ("sta","frd","dat"):
            p=corrected/("full_tri6."+ext)
            if not p.is_file() or not p.stat().st_size:
                raise RuntimeError("Missing actual research ccx "+ext)
        sta=(corrected/"full_tri6.sta").read_text(errors="replace").upper()
        if ("THE ANALYSIS HAS COMPLETED SUCCESSFULLY" not in sta and
            "SUMMARY OF JOB INFORMATION" not in sta):
            raise RuntimeError("Experimental solver STA success not verified")
        results=parse_frd_results(corrected/"full_tri6.frd",set(nodes))
        if results["maximum_displacement_mm"]<=0 or results["maximum_nodal_von_mises_mpa"]<=0:
            raise RuntimeError("Invalid actual full surface field")
        rf=observed_fixed_rf(corrected/"full_tri6.dat",fixed)
        checks=reaction_convention_screen(nodes,fixed,forces,rf)

        # NEW production opt-in must independently generate the exact same
        # C3D10 *NODE/*ELEMENT/*CLOAD deck, not just emulate a research INP.
        opt_case=copy.deepcopy(case)
        opt_case["mesh_request"]["traction_model"]="straight_tri6_full_consistent"
        opt_case["case_sha256"]=hashlib.sha256(
            json.dumps(opt_case,sort_keys=True).encode()).hexdigest()
        opt_dir=folder/"production_opt_in_full_tri6"
        opt_dir.mkdir(parents=True,exist_ok=True)
        opt_result=run_real_fea(step,opt_case,model,opt_dir)
        opt_deck_sha=sha256(opt_dir/"geofield_case.inp")
        if opt_deck_sha!=sha256(deck):
            raise RuntimeError("Production opt-in CLOAD mesh differs from independently assembled real deck")
        if opt_result["mesh"].get("traction_model")!="straight_tri6_full_consistent":
            raise RuntimeError("Production result does not preserve chosen traction identity")
        reaction=opt_result["support_reaction_equilibrium_audit"]
        if (reaction.get("checked") is not True or
            reaction.get("status")!="static_force_and_moment_balanced" or
            not reaction.get("constrained_cload_nodes")):
            raise RuntimeError("Production fixed CLOAD support reaction subtraction failed")
        opt_metrics=opt_result["results"]
        for key,other in (("maximum_displacement_mm",results["maximum_displacement_mm"]),
                          ("maximum_nodal_von_mises_mpa",results["maximum_nodal_von_mises_mpa"])):
            if not math.isclose(opt_metrics[key],other,rel_tol=1e-6,abs_tol=1e-8):
                raise RuntimeError("Production opt-in and independent CalculiX A/B disagree: "+key)
        (opt_dir/"result.json").write_text(json.dumps(opt_result,indent=2),encoding="utf8")
        row={
            "target_mesh_mm":size,
            "cad_sha256":case["cad_sha256"],
            "case_sha256":case["case_sha256"],
            "element_type":"C3D10",
            "same_exact_element_mesh_for_AB":True,
            "production_opt_in_verified":{
                "case_sha256":opt_case["case_sha256"],
                "traction_model":opt_result["mesh"]["traction_model"],
                "INP_matches_independent_full_traction":True,
                "solver_metrics_match_independent":True,
                "support_reactions_corrected_and_balanced":True,
                "correction_for_fixed_cload_nodes":reaction["constrained_cload_nodes"],
                "force_residual_n":reaction["force_residual_magnitude_n"],
                "moment_residual_n_mm":reaction["moment_residual_magnitude_n_mm"],
                "mesh_field_available":opt_result["field_visualization"]["available"],
            },
            "original_production_result":{
                "max_displacement_mm":production["results"]["maximum_displacement_mm"],
                "max_nodal_Mises_MPa":production["results"]["maximum_nodal_von_mises_mpa"],
            },
            "research_full_triangle_load_result":{
                "max_displacement_mm":results["maximum_displacement_mm"],
                "max_nodal_Mises_MPa":results["maximum_nodal_von_mises_mpa"],
            },
            "traction_geometry_audit":audit,
            "deck_integrity":deck_audit,
            "RF_conventions_unresolved":checks,
            "solver_outputs_sha256":{ext:sha256(corrected/("full_tri6."+ext))
                                      for ext in ("inp","sta","frd","dat")},
        }
        rows.append(row)
        print("REAL_C3D10_TRACTION_AB="+json.dumps(row),flush=True)
    def changes(k):
        return [relative_percent(row["research_full_triangle_load_result"][k],
                                 other["research_full_triangle_load_result"][k])
                for row,other in zip(rows,rows[1:])]
    final={
        "status":"real_C3D10_full_surface_traction_AB_research_only",
        "rows":rows,
        "research_full_traction_adjacent_displacement_change_percent":changes("max_displacement_mm"),
        "research_full_traction_adjacent_Mises_change_percent":changes("max_nodal_Mises_MPa"),
        "production_opt_in_available_on_feature_branch":True,
        "production_solver_released":False,
        "numeric_convergence_certified":False,
        "engineering_safety_certified":False,
        "local_stress_exactness_certified":False,
        "windows_verified":False,
        "note":"Study compares two actual CCX decks on each identical C3D10 mesh, not interchangeable verified production FEA runs.",
    }
    (base/"summary.json").write_text(json.dumps(final,indent=2),encoding="utf8")
    print("REAL_C3D10_FULL_TRACTION_RESEARCH="+json.dumps(final),flush=True)
    return final


if __name__ == "__main__":
    run()
