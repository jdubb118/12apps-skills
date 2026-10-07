"""indesign-package / package: archive the designer folder, expand the archive into a temp dir and re-run the integrity
gate there, so links are proven to resolve from the expanded location (which is how the designer opens it).
usage: python3 package.py <job.json>      -> <out_dir>/<name>_InDesign_<YYYY-MM-DD>.zip"""
import sys, os, zipfile, tempfile, datetime, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_job
from check import integrity

job = load_job(sys.argv[1])
folder = job['name'] + '_InDesign'
pkg = os.path.join(job['out_dir'], folder)
zp = os.path.join(job['out_dir'], f"{folder}_{datetime.date.today().isoformat()}.zip")
if os.path.exists(zp): os.remove(zp)
n = 0
with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(pkg):
        dirs.sort()
        for fn in sorted(files):
            if fn == '.DS_Store' or fn.startswith('._'): continue
            full = os.path.join(root, fn)
            arc = os.path.join(folder, os.path.relpath(full, pkg))
            z.write(full, arc, compress_type=zipfile.ZIP_STORED if fn.lower().endswith(('.idml', '.jpg', '.jpeg', '.png', '.pdf')) else zipfile.ZIP_DEFLATED)
            n += 1
tmp = tempfile.mkdtemp(prefix='idpkg-')
bad = 0
try:
    with zipfile.ZipFile(zp) as z:
        assert z.testzip() is None, 'corrupt archive'
        z.extractall(tmp)
    for d in job['documents']:
        errs, _ = integrity(os.path.join(tmp, folder, d['idml'] + '.idml'))
        print(f"  expanded {d['idml']}.idml: {'links + references OK' if not errs else 'ERRORS ' + '; '.join(errs[:4])}"); bad += bool(errs)
finally:
    shutil.rmtree(tmp)
print(f'{zp}  ({os.path.getsize(zp):,} bytes, {n} files)')
sys.exit(1 if bad else 0)
