#!/usr/bin/env python3
"""sync-footage.py — after any clip.py (re)cut: rewrite every footage <video>'s data-duration in index.html from the
clip's JSON and regenerate assets/footage/manifest.js (window.FOOTAGE). A stale data-duration is silent: the clip
just stops early and the scene shows its dark ground under the last frames of the wipe.

    python3 sync-footage.py <piece-dir>
"""
import glob, json, os, re, sys
P = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
html = open(os.path.join(P, "index.html")).read()
meta = {os.path.basename(j)[:-5]: json.load(open(j)) for j in glob.glob(os.path.join(P, "assets/footage/*.json"))}
if not meta: sys.exit("no assets/footage/*.json")
n = 0
def fix(m):
    global n
    key = m.group(2); d = meta.get(key, {}).get("dur")
    if d is None: return m.group(0)
    n += 1
    return f'{m.group(1)}assets/footage/{key}{m.group(3)}" data-start="{m.group(4)}" data-duration="{d:.4f}"'
html2 = re.sub(r'(src=")assets/footage/([a-z0-9_-]+?)((?:-subject\.webm|\.mp4))" data-start="([\d.]+)" data-duration="[\d.]+"', fix, html)
open(os.path.join(P, "index.html"), "w").write(html2)
open(os.path.join(P, "assets/footage/manifest.js"), "w").write("window.FOOTAGE=" + json.dumps(meta) + ";")
print(f"synced {n} video tags · manifest: " + ", ".join(f"{k} {v['dur']}s" for k, v in sorted(meta.items())))
