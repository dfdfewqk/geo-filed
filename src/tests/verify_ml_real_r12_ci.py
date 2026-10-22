"""Run real bundled R12 model inference on the public L bracket STEP.

CI supplies only the Python runtime environment adapter which normally comes
from the existing installed GeoField engine. CAD feature extraction, the model,
OCP and scikit-learn are genuine and are never mocked.
"""
from pathlib import Path
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import types

ROOT=Path(__file__).resolve().parents[1]
PAYLOAD=ROOT/'payload'
STEP=ROOT.parent/'fixtures'/'L_bracket.step'
sys.path.insert(0,str(PAYLOAD))

# The repository is a drop-in overlay for the user's installed GeoField runtime.
# Validate actual import capabilities without requiring that private runtime.
if 'engine_runtime' not in sys.modules:
    module=types.ModuleType('engine_runtime')
    def probe(env, requirements):
        cmd=[sys.executable,'-c','import importlib; '+ '\n'.join('importlib.import_module('+repr(n)+')' for n in requirements)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
        return {'ok':p.returncode==0,'path':sys.executable,
                'modules':({name:True for name in requirements} if p.returncode==0 else {}),
                'error':p.stderr[-300:]}
    module.engine_python=probe
    module.prepare_python_environment=lambda executable:dict(os.environ)
    sys.modules['engine_runtime']=module
import ml_r12_bridge


def main():
    if not STEP.is_file():raise RuntimeError('Repository reference STEP missing')
    pre=ml_r12_bridge.preflight(PAYLOAD)
    if not pre['available']:
        raise RuntimeError('Real R12 runtime unavailable: '+repr(pre))
    start_sha=hashlib.sha256(STEP.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='geofield-ml-real-') as d:
        result=ml_r12_bridge.execute(PAYLOAD,STEP,Path(d))
        assert result['cad_sha256']==start_sha
        assert result['candidate_count']==len(result['predictions'])
        assert result['candidate_count']>0
        assert result['geometry_certified'] is False and result['fea_calculated'] is False
        assert result['status']=='research_not_for_production'
        assert hashlib.sha256(STEP.read_bytes()).hexdigest()==start_sha
        print('ACTUAL_R12_MODEL_INFERENCE='+json.dumps({'status':result['status'],
              'candidate_count':result['candidate_count'],'cad_sha256':start_sha,
              'model_sha256':ml_r12_bridge.EXPECTED_MODEL_SHA256,
              'research_only':True,'original_step_preserved':True},ensure_ascii=False))

if __name__=='__main__':main()
