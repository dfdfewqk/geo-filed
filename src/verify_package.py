# -*- coding: utf-8 -*-
"""GeoField R12.13 QA readable local integrity verification. No network or installing."""
import hashlib,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent
EXPECTED={'geofield_port_recovery.py': '3fe90420ade765a3ffffc9846ba6dfffd1cad143fd747f047e02cc58dc984c2e', 'bootstrap.py': '6e62e2b91c51924af48ff5f87db26246da4462587446cdba3fcaadfd45d86d25', 'installer.py': '17ab40f2a0ed8b2353bd788f7de3266c1bdc57d40a08b8c08c6abb1ef02a72b2', 'manifest.json': '452a954487785f56472a95a01d59de4ac7c83a74a937bb860965194dafbcd280', 'payload/GeoField_CAD_Analysis.py': 'a4503bd4bb7b23765fbd037275dc133725cfd80db2977ab05a684e3abb427f41', 'payload/frontend/index.html': '96c285f7b81bcc8fa96227be89e72751effdbe06b801f4282479342104563a7b', 'payload/frontend/cad.js': '3a8aa57879a15cda900673dd619cd6181658d90532c77e30f7faee8047f52b48', 'payload/fea_result_trust_gate.py': 'a899ab6011d9fbf6f344664361f474b0ba7800d2cdfbf938a7e2f4272fb462ad', 'payload/fea_solver.py': 'a7aa04ffa5930f925eb1d738551629b24b44b5d117f22165c0d9657e5520d7cf', 'payload/ml/r12_research/research_model.joblib': 'df51d702ee77fb9efdc2de730f679f62d18e652c9d6279736e4deef353535dd0'}
def main():
    for name,expected in EXPECTED.items():
        f=BASE/name
        if not f.is_file() or f.is_symlink():
            print('[ERROR] Missing or linked file:',name,flush=True);return 11
        if hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
            print('[ERROR] SHA-256 mismatch:',name,flush=True);return 12
    try:
        from installer import DirectoryBundle,verify_bundle
        manifest=verify_bundle(DirectoryBundle(BASE))
        print('[OK] R12.13 QA package verified:',len(manifest['files']),'payload files',flush=True)
        return 0
    except Exception as e:
        print('[ERROR] Package manifest invalid:',str(e),flush=True);return 13
if __name__=='__main__':sys.exit(main())
