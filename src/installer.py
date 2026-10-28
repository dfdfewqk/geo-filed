# -*- coding: utf-8 -*-
"""GeoField R12 additive research UI integration. No data, FEA, weights overwritten."""
from pathlib import Path
import os,sys,hashlib,json,datetime,uuid,shutil,socket
from pathlib import PurePosixPath

def sha(data):return hashlib.sha256(data).hexdigest()
def log(*a):print(*a,flush=True)


# Minimal transparent package reader: no embedded archive, no shell decoding.
class DirectoryBundle:
    def __init__(self, directory):
        self.directory=Path(directory).resolve()
    def read(self, name):
        parts=PurePosixPath(name).parts
        if (not parts or name.startswith('/') or name.startswith('\\') or
            any(p in ('.','..') for p in parts) or
            any(':' in p or '\\' in p for p in parts)):
            raise ValueError('Unsafe package path')
        location=self.directory.joinpath(*parts)
        if location.is_symlink() or any(p.is_symlink() for p in location.parents if p!=self.directory.parent):
            raise ValueError('Package contains symlink: '+name)
        if not location.is_file():raise FileNotFoundError(name)
        return location.read_bytes()

ALLOWED_TARGETS=frozenset(('GeoField_CAD_Analysis.py','frontend/index.html',
    'frontend/cad.js','ml_r12_bridge.py','ml_env_resolver.py',
    'ml/r12_research/__init__.py','ml/r12_research/features.py',
    'ml/r12_research/train_eval.py','ml/r12_research/build_data.py',
    'ml/r12_research/worker.py','ml/r12_research/research_model.joblib',
    'ml/r12_research/report.json','fea_solver.py','fea_result_trust_gate.py',
    'fea_convergence.py','fea_mesh_series.py','fea_load_moment.py',
    'fea_compare.py','fea_history_a03.py','fea_history_delete_a04.py',
    'fea_field_a06.py','fea_report_a08.py'))

def verify_bundle(package):
    """Fail closed before touching the installed program, even on reinstall."""
    manifest=json.loads(package.read('manifest.json'))
    if manifest.get('runtime_id')!='8a9ac53a821a0eb5':
        raise RuntimeError('Unrecognized GeoField runtime id')
    files=manifest.get('files')
    if not isinstance(files,dict) or set(files)!=ALLOWED_TARGETS:
        raise RuntimeError('Unexpected payload files in manifest')
    for name,meta in files.items():
        data=package.read('payload/'+name)
        if (type(meta) is not dict or len(meta.get('to',''))!=64 or
            sha(data)!=meta['to'] or len(data)!=meta['bytes']):
            raise RuntimeError('Package file integrity mismatch: '+name)
    return manifest

def _atomic_json_write(destination, payload):
    """Durable local journal, written before the first installed-file replacement."""
    stage=destination.with_name(destination.name+'.writing-'+uuid.uuid4().hex)
    try:
        with stage.open('x', encoding='utf8') as stream:
            json.dump(payload,stream,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage,destination)
    finally:
        stage.unlink(missing_ok=True)


def recover_interrupted_install(root, target):
    """Restore a verifiable all-old state after a prior abrupt process termination.

    Never trust arbitrary paths in a journal or restore when another process has
    modified the affected files since the interruption. Call only with port free.
    """
    base=root/'backups'
    if not base.is_dir():
        return 0
    recovered=0
    for folder in sorted(base.glob('r12-research-integrated-*')):
        if folder.is_symlink():
            raise RuntimeError('Interrupted-install backup directory is a symlink: '+str(folder))
        journal=folder/'install_journal.json'
        if not journal.is_file() or journal.is_symlink():
            continue
        try:
            doc=json.loads(journal.read_text(encoding='utf8'))
        except (OSError,ValueError) as exc:
            raise RuntimeError('Unreadable install journal; manual review required: '+str(journal)) from exc
        if doc.get('state')!='pending':
            continue
        entries=doc.get('entries')
        if (not isinstance(entries,list) or not entries or
            doc.get('runtime_id')!=target.name):
            raise RuntimeError('Invalid interrupted-install journal: '+str(journal))
        restored=[]
        for item in entries:
            if not isinstance(item,dict) or item.get('path') not in ALLOWED_TARGETS:
                raise RuntimeError('Untrusted interrupted-install target: '+str(journal))
            rel=Path(item['path'])
            dst=target/rel
            if dst.is_symlink() or any(part.is_symlink() for part in list(dst.parents) if part!=Path('/')):
                raise RuntimeError('Interrupted-install target uses symlinks: '+str(dst))
            old=item.get('before_sha256')
            new=item.get('installed_sha256')
            if (old is not None and (not isinstance(old,str) or len(old)!=64) or
                not isinstance(new,str) or len(new)!=64):
                raise RuntimeError('Invalid interrupted-install checksums: '+str(journal))
            current=sha(dst.read_bytes()) if dst.is_file() else None
            if current not in (old,new):
                raise RuntimeError('Interrupted install has unrecognized edited file: '+str(dst))
            previous=None
            if old is not None:
                backup=folder/rel
                if not backup.is_file() or backup.is_symlink() or any(p.is_symlink() for p in backup.parents):
                    raise RuntimeError('Interrupted-install backup missing or linked: '+str(backup))
                previous=backup.read_bytes()
                if sha(previous)!=old:
                    raise RuntimeError('Interrupted-install backup mismatch: '+str(backup))
            restored.append((dst,previous))
        # Validate every file and every backup before touching the first target.
        for dst,previous in restored:
            if previous is None:
                dst.unlink(missing_ok=True)
            elif sha(dst.read_bytes())!=sha(previous):
                stage=dst.with_name('.'+dst.name+'.recovery-'+uuid.uuid4().hex+'.tmp')
                try:
                    with stage.open('xb') as handle:
                        handle.write(previous);handle.flush();os.fsync(handle.fileno())
                    os.replace(stage,dst)
                finally:
                    stage.unlink(missing_ok=True)
        _atomic_json_write(journal,{**doc,'state':'recovered'})
        recovered+=1
    if recovered:
        log('[RECOVERED]',recovered,'interrupted installation(s), based on verified backups')
    return recovered


def apply(zipfile_obj,localappdata=None,receipt=None,approved_unknown_hashes=None):
    """Apply signed-by-hash candidate. Unknown local source requires explicit,
    exact SHA-256 approval from bootstrap after separate dependency preflight.
    Original local source is backed up and survives any failed updated startup.
    """
    approved_unknown_hashes={} if approved_unknown_hashes is None else approved_unknown_hashes
    if (not isinstance(approved_unknown_hashes,dict) or
        any(name not in ALLOWED_TARGETS or not name.endswith(('.py','.js','.html')) or
            not isinstance(digest,str) or len(digest)!=64 or
            any(c not in '0123456789abcdef' for c in digest)
            for name,digest in approved_unknown_hashes.items())):
        raise RuntimeError('Invalid explicit local source approval map')
    manifest=verify_bundle(zipfile_obj)
    if localappdata is None:
        localappdata=os.environ.get('LOCALAPPDATA')
        if not localappdata:raise RuntimeError('Windows LOCALAPPDATA not found')
    root=Path(localappdata)/'GeoFieldCAD'
    target=root/'onefile_runtime'/manifest['runtime_id']
    if not target.is_dir() or target.is_symlink():raise RuntimeError('Expected installed GeoField runtime folder not found')
    if any(p.is_symlink() for p in [target.parent,root,root.parent]):raise RuntimeError('Unsafe symlink root')
    if not (target/'engine_runtime.py').is_file() or not (target/'fea_solver.py').is_file():
        raise RuntimeError('This is not the matching GeoField runtime')
    if os.name=='nt':
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1',8600))==0:
                raise RuntimeError('Close GeoField server CMD first (port 8600 is open)')
    recover_interrupted_install(root, target)
    changed=[];errors=[]
    for name,meta in manifest['files'].items():
        path=target/name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p!=Path('/')):
            errors.append(name+': symlink');continue
        old=sha(path.read_bytes()) if path.is_file() else None
        if old==meta['to']:continue
        known_prior=(old==meta.get('from') or old in meta.get('compatible_from',[]) or
                     (old is None and meta.get('allow_missing_from') is True))
        consented_local=(old is not None and old==approved_unknown_hashes.get(name) and
                         name.endswith(('.py','.js','.html')))
        if not known_prior and not consented_local:
            errors.append(name+': installed file differs from verified version')
            continue
        payload=zipfile_obj.read('payload/'+name)
        if sha(payload)!=meta['to']:raise RuntimeError('Payload checksum mismatch: '+name)
        changed.append((path,payload,old))
    if errors:raise RuntimeError('Refusing to overwrite unknown source: '+' | '.join(errors))
    if not changed:
        if receipt is not None: receipt.update({'backup': None, 'changed': [], 'root': str(target)})
        log('[OK] ALREADY_INSTALLED: exact source hashes verified');return 0
    token=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    backup=root/'backups'/('r12-research-integrated-'+token)
    backup.mkdir(parents=True,exist_ok=False)
    journal=backup/'install_journal.json'
    staged=[];applied=[]
    try:
        for target_path,data,old in changed:
            if old is not None:
                b=backup/target_path.relative_to(target)
                b.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(target_path,b)
                if sha(b.read_bytes())!=old:raise RuntimeError('Backup hash mismatch: '+str(target_path))
            target_path.parent.mkdir(parents=True,exist_ok=True)
            stage=target_path.with_name('.'+target_path.name+'.'+token+'.tmp')
            with stage.open('xb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            staged.append(stage)
            if sha(stage.read_bytes())!=sha(data):raise RuntimeError('Staged file checksum mismatch: '+str(stage))
        (backup/'manifest_before.json').write_text(json.dumps({str(p.relative_to(target)):old for p,_,old in changed},indent=2),encoding='utf8')
        _atomic_json_write(journal,{
            'state':'pending','runtime_id':target.name,
            'entries':[{'path':str(path.relative_to(target)).replace('\\','/'),
                        'before_sha256':old,'installed_sha256':sha(data)}
                       for path,data,old in changed]})
        for target_path,data,old in changed:
            stage=next(s for s in staged if s.name.startswith('.'+target_path.name+'.') and s.parent==target_path.parent)
            os.replace(stage,target_path)
            applied.append((target_path,old))
        for target_path,data,_ in changed:
            if sha(target_path.read_bytes())!=sha(data):raise RuntimeError('Post-apply mismatch: '+str(target_path))
        _atomic_json_write(journal,{**json.loads(journal.read_text(encoding='utf8')),'state':'installed'})
    except BaseException:
        rollback_errors=[]
        for target_path,old in reversed(applied):
            try:
                if old is None:target_path.unlink(missing_ok=True)
                else:
                    b=backup/target_path.relative_to(target)
                    shutil.copy2(b,target_path)
                    if sha(target_path.read_bytes())!=old:raise RuntimeError('Rollback mismatch')
            except Exception as err:rollback_errors.append(str(target_path)+' : '+str(err))
        if rollback_errors:raise RuntimeError('MANUAL ROLLBACK REQUIRED '+repr(rollback_errors))
        if journal.exists():
            _atomic_json_write(journal,{**json.loads(journal.read_text(encoding='utf8')),'state':'recovered'})
        raise
    finally:
        for temp in staged:temp.unlink(missing_ok=True)
    if receipt is not None:
        receipt.update({'root': str(target), 'backup': str(backup),
            'journal': str(journal),
            'changed': [{'path': str(p.relative_to(target)), 'before_sha256': old,
                         'installed_sha256': sha(data)} for p,data,old in changed]})
    log('[OK] INSTALLED: GeoField main UI + R12 research analysis button')
    log('[OK] File hashes verified; updated files:',len(changed))
    log('[BACKUP]',str(backup))
    log('[SAFE] STEP / SQLite / FEA INP/STA/FRD / existing checkpoint not changed')
    log('[NEXT] Restart GeoField, Ctrl+F5, choose STEP and CAD verification tab')
    log('[LIMIT] Real Windows modules and browser still require confirmation')
    return 0

def rollback_install(receipt):
    """Revert ONLY this invocation's verified code changes; never touch user data.

    Every installed file must still match the bytes we wrote, otherwise stop
    before restoring anything. Prior originals must match the backup hashes.
    """
    changed = receipt.get('changed', [])
    if not changed:
        log('[ROLLBACK] No files were changed by this invocation.')
        return 0
    target = Path(receipt['root'])
    backup = Path(receipt['backup'])
    originals=[]
    for item in changed:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() not in ALLOWED_TARGETS:
            raise RuntimeError('Unsafe rollback relative path')
        destination = target / relative
        if destination.is_symlink() or any(p.is_symlink() for p in destination.parents):
            raise RuntimeError('Rollback refused: installed path contains symlink: ' + item['path'])
        if not destination.is_file() or destination.is_symlink():
            raise RuntimeError('Rollback refused: installed file missing/linked: ' + item['path'])
        if sha(destination.read_bytes()) != item['installed_sha256']:
            raise RuntimeError('Rollback refused: installed file changed since upgrade: ' + item['path'])
        old_sha = item['before_sha256']
        previous = None
        if old_sha is not None:
            saved = backup / relative
            if not saved.is_file() or saved.is_symlink() or any(p.is_symlink() for p in saved.parents):
                raise RuntimeError('Rollback backup missing or linked: ' + item['path'])
            previous = saved.read_bytes()
            if sha(previous) != old_sha:
                raise RuntimeError('Rollback backup hash mismatch: ' + item['path'])
        originals.append((destination,previous))
    token = uuid.uuid4().hex
    stages=[]
    try:
        for destination,previous in originals:
            if previous is not None:
                stage=destination.with_name('.'+destination.name+'.rollback-'+token+'.tmp')
                with stage.open('xb') as f:
                    f.write(previous);f.flush();os.fsync(f.fileno())
                stages.append((destination,stage))
        stage_dict=dict(stages)
        for destination,previous in originals:
            if previous is None: destination.unlink()
            else: os.replace(stage_dict[destination],destination)
        log('[ROLLBACK] Restored',len(originals),'changed code files. User engineering data untouched.')
    finally:
        for _,stage in stages: stage.unlink(missing_ok=True)
    journal=receipt.get('journal')
    if journal and Path(journal).is_file():
        record=json.loads(Path(journal).read_text(encoding='utf8'))
        _atomic_json_write(Path(journal),{**record,'state':'reverted'})
    return len(originals)

def main():
    try:return apply(DirectoryBundle(Path(__file__).resolve().parent))
    except Exception as err:
        log('[ERROR] INSTALL NOT APPLIED OR ROLLED BACK:',str(err));return 1

if __name__=='__main__':sys.exit(main())
