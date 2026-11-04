"""Actual Gmsh + CalculiX D5.5-vs-D6 synthetic L-bracket solver acceptance.

Generates two *synthetic/public* STEP solids in temp CI workspace, uses the
PRODUCTION fea_solver.run_real_fea twice (never fake CCX/FRD/STA), then passes
the actual emitted INP node/support/load decks through the production
cross-geometry physical support/load/moment screen. Never accesses user data,
private model weights, Windows, SQLite, network or paid API.
This is not the user's private STEP, SQLite archive or UI integration test.
"""
from __future__ import annotations
import ast
import hashlib
import json
import math
import os
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/"src"))
sys.path.insert(0,str(REPO/"src"/"payload"))
sys.path.insert(0,str(REPO/"src"/"tests"/"fea_ci_dependencies"))
from fea_solver import run_real_fea,sha256
from fea_load_moment import screen_two_geometry_verified_inp
import gmsh

EVIDENCE=REPO/"_real_d6_two_solver_evidence"
RUNS=(("1"*32,2.75),("2"*32,3.0))
FORCE=49.03325

def create_public_variant(path, radius):
    """Genuine OCC STEP through-hole geometry, never user's source STEP."""
    gmsh.initialize(["-nopopup"])
    try:
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("synthetic_L_D"+str(radius))
        occ=gmsh.model.occ
        base=occ.addBox(0,0,0,50,30,5)
        wall=occ.addBox(0,0,0,5,30,50)
        fused,_=occ.fuse([(3,base)],[(3,wall)],
                         removeObject=True,removeTool=True)
        cutters=[(3,occ.addCylinder(x,y,-1,0,0,7,radius))
                 for x in (15,35) for y in (8,22)]
        cut,_=occ.cut(fused,cutters,removeObject=True,removeTool=True)
        occ.synchronize()
        solids=gmsh.model.getEntities(3)
        if len(cut)!=1 or len(solids)!=1:
            raise AssertionError("Generated OCC variant must contain exactly one solid")
        before=float(occ.getMass(3,solids[0][1]))
        if not 5000<before<15000:
            raise AssertionError("Invalid public bracket solid volume")
        gmsh.write(str(path))
        if not path.is_file() or path.stat().st_size<100:
            raise AssertionError("OCC STEP was not exported")
        return before
    finally:
        gmsh.finalize()

def face_model(step):
    gmsh.initialize(["-nopopup"])
    try:
        gmsh.option.setNumber("General.Terminal",0)
        gmsh.model.add("independently_imported_STEP_faces")
        gmsh.model.occ.importShapes(str(step),highestDimOnly=False)
        gmsh.model.occ.synchronize()
        faces=[]
        for dim,tag in gmsh.model.getEntities(2):
            center=list(map(float,gmsh.model.occ.getCenterOfMass(dim,tag)))
            area=float(gmsh.model.occ.getMass(dim,tag))
            faces.append((int(tag),center,area))
        if len(faces)<10:
            raise AssertionError("STEP should contain actual cylindrical/planar faces")
        def choose(which,axis,value,minarea):
            found=[i+1 for i,(_,xyz,area) in enumerate(faces)
                   if abs(xyz[axis]-value)<1e-5 and area>=minarea
                   and ((which=="fixed" and abs(xyz[1]-15)<.01)
                        or (which=="loaded" and abs(xyz[1]-15)<.01))]
            if len(found)!=1:
                raise AssertionError("Cannot independently select unique "+
                                     which+" face: "+repr(found))
            return found[0]
        # True geometric x=0 support wall and remote x=50 loaded base edge.
        # These face positions are unchanged by the four interior hole radii.
        fixed=choose("fixed",0,0.,1450.)
        loaded=choose("loaded",0,50.,140.)
        signatures=[{"face_id":i+1,"center_mm":xyz,"area_mm2":area}
                    for i,(_,xyz,area) in enumerate(faces)]
        return {"sha256":sha256(step),
                "mesh":{"face_ids":[s["face_id"] for s in signatures],
                        "face_signatures":signatures}},fixed,loaded
    finally:
        gmsh.finalize()

def solve_case(step,rid,radius):
    model,fixed,loaded=face_model(step)
    token=model["sha256"]
    case={"schema":"geofield-fea-case-v1",
          "status":"configuration_prepared_solver_not_connected",
          "cad_sha256":token,
          "case_sha256":hashlib.sha256(
             ("synthetic-public-D"+str(radius)+":"+token+
              ":"+str(fixed)+":"+str(loaded)).encode()).hexdigest(),
          "material":{"young_modulus_mpa":200000.,"poisson_ratio":0.3},
          "mesh_request":{"target_element_size_mm":3.5,
                          "element_type":"C3D4"},
          "boundary_conditions":{"fixed_face_ids":[fixed],
              "load_face_ids":[loaded],
              "total_force_n":FORCE,
              "force_direction_unit":[0.,0.,-1.]},
          "self_weight_reference":{"applied_to_solver":False}}
    directory=EVIDENCE/"fea_runs"/rid
    directory.mkdir(parents=True,exist_ok=True)
    (directory/"input_case.json").write_text(json.dumps(case,indent=2),encoding="utf-8")
    result=run_real_fea(step,case,model,directory)
    (directory/"result.json").write_text(
         json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),
         encoding="utf-8")
    if result.get("status")!="solver_executed_result_parsed":
        raise AssertionError("Actual CalculiX result was not parsed")
    rf=result.get("support_reaction_equilibrium_audit") or {}
    if rf.get("checked") is not True:
        raise AssertionError("Actual CalculiX reaction equilibrium did not pass")
    for suffix in (".inp",".sta",".frd",".dat"):
        artifact=directory/("geofield_case"+suffix)
        if not artifact.is_file() or artifact.stat().st_size<20:
            raise AssertionError("Missing actual CalculiX "+suffix+" file")
    stress=result["results"]["maximum_nodal_von_mises_mpa"]
    disp=result["results"]["maximum_displacement_mm"]
    if not all(isinstance(x,(int,float)) and math.isfinite(x) and x>0
               for x in (stress,disp)):
        raise AssertionError("No real stress/displacement numbers from solver")
    print("ACTUAL_CALCULIX_D6_CASE="+json.dumps({
      "hole_diameter_mm":2*radius,"sha":token[:12],
      "fixed_face_id_for_this_STEP":fixed,
      "load_face_id_for_this_STEP":loaded,
      "actual_nodes":result["mesh"]["node_count"],
      "actual_tetrahedra":result["mesh"]["tetrahedron_count"],
      "actual_max_stress_mpa":stress,
      "actual_max_displacement_mm":disp},ensure_ascii=False),flush=True)
    return {
      "snapshot_id":("3"*32 if rid==RUNS[0][0] else "4"*32),
      "run_id":rid,"cad_sha256":token,"case_sha256":case["case_sha256"],
      "cad_name":step.name,
      "evidence":"real_solver_files_revalidated",
      "max_stress_mpa":stress,"max_displacement_mm":disp,
      "mesh_target_mm":3.5,
      "mesh_node_count":result["mesh"]["node_count"],
      "mesh_tetrahedron_count":result["mesh"]["tetrahedron_count"],
      # Test true production optional-label defaults; no labels fabricated.
      "material":None,"analysis_type":None,"load_interpretation":None,
      "young_modulus_mpa":200000.,"poisson_ratio":0.3,
      "fixed_faces":[fixed],"load_faces":[loaded],
      "force_n":FORCE,"direction":[0.,0.,-1.],
      "external_mass_kg":None,"gravity_density_kg_m3":None,
      "gravity_mm_s2":None,"gravity_direction":None,"self_weight_applied":False,
      "element_type":result["mesh"]["element_type"],
      "traction_model":result["mesh"]["traction_model"],
      "solver":result["solver"],"mesher":result["mesher"]}

def load_production_comparator():
    """No need to install Windows-only fea_restore to test real numeric gate."""
    src=(REPO/"src"/"fea_compare.py").read_text(encoding="utf-8")
    func=next(n for n in ast.parse(src).body if
              isinstance(n,ast.FunctionDef) and
              n.name=="compare_d6_geometry_variant")
    scope={"math":math,"re":__import__("re")}
    exec(compile(ast.fix_missing_locations(
          ast.Module(body=[func],type_ignores=[])),
          str(REPO/"src"/"fea_compare.py"),"exec"),scope)
    return scope["compare_d6_geometry_variant"]

def main():
    EVIDENCE.mkdir(exist_ok=True)
    cases=[]
    for rid,radius in RUNS:
        step=EVIDENCE/("synthetic_L_d"+str(2*radius).replace(".","_")+".step")
        volume=create_public_variant(step,radius)
        row=solve_case(step,rid,radius)
        row["solid_volume_mm3"]=volume
        cases.append(row)
    if cases[0]["cad_sha256"]==cases[1]["cad_sha256"]:
        raise AssertionError("Two independently generated STEP files are identical")
    physics=screen_two_geometry_verified_inp(EVIDENCE,cases[0],cases[1])
    comp=load_production_comparator()
    rows={item["snapshot_id"]:item for item in cases}
    def actual_solved_row(_db,_jobs,sid):
        return rows[sid]
    synthetic_provenance={
      "source":"server_OCP_postexport_reverified",
      "operation":"lbracket_d55_to_d60_4_through_copy_v1",
      "source_sha256":cases[0]["cad_sha256"],
      "variant_sha256":cases[1]["cad_sha256"],
      "geometry_only_verified":True,
      "needs_new_face_selection":True,
      "structural_improvement_verified":False}
    comparison=comp(None,EVIDENCE,cases[0]["snapshot_id"],
                    cases[1]["snapshot_id"],synthetic_provenance,
                    load_side=actual_solved_row)
    if comparison["support_location_screen_passed"] is not True:
        raise AssertionError("Actual fixed support location did not pass screen")
    if comparison["applied_load_moment_screen_passed"] is not True:
        raise AssertionError("Actual applied loads/moment did not pass screen")
    if (comparison["design_improvement_verified"] is not False or
        comparison["structural_safety_certified"] is not False or
        comparison["reaction_and_applied_moment_equivalence_verified"] is not False):
        raise AssertionError("Descriptive check was incorrectly labelled certified")
    public={
      "real_calculix_runs":2,"synthetic_not_user_step":True,
      "independent_user_sqlite_history_not_tested":True,
      "source_STEP_exported_by":"Gmsh_OCC_synthetic_test",
      "geometry_change_diameter_mm":[5.5,6.0],
      "compared_max_stress_mpa":[x["max_stress_mpa"] for x in cases],
      "compared_max_displacement_mm":[x["max_displacement_mm"] for x in cases],
      "real_inp_support_load_moment_screen":physics,
      "improvement_verified":False,"safety_certified":False,
      "missing_optional_fields":comparison["missing_optional_input_labels"]}
    (EVIDENCE/"acceptance.json").write_text(
      json.dumps(public,indent=2,ensure_ascii=False,allow_nan=False),
      encoding="utf-8")
    print("GEOFIELD_TWO_ACTUAL_SOLVERS_D6_ACCEPTANCE="+
          json.dumps(public,ensure_ascii=False),flush=True)
    return public

if __name__=="__main__":
    main()
