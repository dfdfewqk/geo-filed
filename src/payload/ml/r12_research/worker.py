# -*- coding: utf-8 -*-
"""Read-only R12 process for an explicitly supplied STEP, never an FEA solver."""
import argparse,hashlib,json,os
from pathlib import Path
from .train_eval import research_predict

def main():
    p=argparse.ArgumentParser();p.add_argument('--step',required=True);p.add_argument('--out',required=True)
    p.add_argument('--model',required=True);p.add_argument('--manifest',required=True)
    a=p.parse_args();step=Path(a.step).resolve();dest=Path(a.out).resolve()
    data=research_predict(step,Path(a.model),Path(a.manifest))
    data['cad_sha256']=hashlib.sha256(step.read_bytes()).hexdigest()
    data['decision_usage']='blocked_diagnostic_only'
    data['is_independent_r12_research']=True
    if data.get('fea_calculated') is not False or data.get('geometry_certified') is not False:
        raise RuntimeError('Research result unexpectedly claims an FEA/geometry certification')
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_name(dest.name+'.new')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(temp,dest)
if __name__=='__main__':main()
