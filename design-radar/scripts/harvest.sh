#!/bin/bash
# Re-scan Awwwards Sites of the Day and rebuild the corpus evidence.
# Usage: bash harvest.sh [workdir]   (default /tmp/awstudy)
# ~6 min for 31 sites. Requires `npm install` in scripts/ (playwright).
set -u
WORK="${1:-/tmp/awstudy}"
SC="$(cd "$(dirname "$0")" && pwd -P)"
SKILL="$(dirname "$SC")"
mkdir -p "$WORK/json"

# NOTE: macOS has no `timeout` / `gtimeout` unless coreutils is installed.
# site-inspect.mjs has its own 45s navigation timeout, so we rely on that.
TO=""
command -v gtimeout >/dev/null && TO="gtimeout 130"

echo "[1/4] fetching SOTD listing"
curl -sS -A "Mozilla/5.0" --max-time 30 \
  "https://www.awwwards.com/websites/sites_of_the_day/" > "$WORK/sotd.html" || exit 1
echo "      $(wc -c < "$WORK/sotd.html") bytes"

echo "[2/4] resolving destination URLs"
python3 - "$WORK" <<'PY'
import re,html,collections,subprocess,sys,json,os
W=sys.argv[1]
SKIP=re.compile(r'(awwwards|w3\.org|instagram|linkedin|youtube|tiktok|pinterest|facebook|twitter|x\.com|google|gstatic|googleapis|cloudflare|schema\.org|vimeo|behance|dribbble|github|apple\.com|paypal|stripe|typekit|adobe|jsdelivr|unpkg|bit\.ly|threads\.net|whatsapp|t\.me|medium\.com|substack)',re.I)
x=html.unescape(open(f'{W}/sotd.html',encoding='utf-8').read())
slugs=[]
for m in re.finditer(r'href="/sites/([a-z0-9\-]+)"',x):
    if m.group(1) not in slugs: slugs.append(m.group(1))
print(f"      {len(slugs)} slugs")
out={}
for s in slugs:
    try:
        h=subprocess.run(['curl','-sS','-A','Mozilla/5.0','--max-time','25',
            f'https://www.awwwards.com/sites/{s}'],capture_output=True,text=True,timeout=45).stdout
    except Exception: out[s]=None; continue
    c=collections.Counter()
    for m in re.finditer(r'https?://([a-z0-9.\-]+)',html.unescape(h)):
        d=m.group(1)
        if SKIP.search(d) or d.count('.')>3: continue
        c[d]+=1
    out[s]='https://'+c.most_common(1)[0][0] if c else None
json.dump(out,open(f'{W}/targets.json','w'),indent=1)
open(f'{W}/pairs.tsv','w').write(''.join(f'{k}\t{v}\n' for k,v in out.items() if v))
print(f"      resolved {sum(1 for v in out.values() if v)}/{len(slugs)}")
PY

echo "[3/4] rendering sites (5 at a time)"
rm -f "$WORK"/json/*
cd "$SC" || exit 1
N=0
while IFS=$'\t' read -r slug url; do
  [ -z "$url" ] && continue
  ( $TO node "$SC/site-inspect.mjs" "$url" --wait 6000 \
      > "$WORK/json/$slug.json" 2>"$WORK/json/$slug.err" ) &
  N=$((N+1)); [ $((N % 5)) -eq 0 ] && wait
done < "$WORK/pairs.tsv"
wait

# Assert non-empty yield — an empty corpus must never pass silently.
OK=0; for f in "$WORK"/json/*.json; do [ -s "$f" ] && OK=$((OK+1)); done
echo "      rendered $OK/$N"
if [ "$OK" -lt $((N / 2)) ]; then
  echo "FAIL: yield $OK/$N is below half — refusing to rewrite corpus.md" >&2
  head -3 "$WORK"/json/*.err 2>/dev/null | head -20 >&2
  exit 1
fi

echo "[4/4] rebuilding references/corpus.md"
python3 - "$WORK" "$SKILL" <<'PY'
import json,glob,os,sys
W,SKILL=sys.argv[1],sys.argv[2]
t=json.load(open(f'{W}/targets.json')); rows=[]
for f in sorted(glob.glob(f'{W}/json/*.json')):
    if os.path.getsize(f)==0: continue
    try: d=json.load(open(f))
    except: continue
    if 'error' in d: continue
    s=os.path.basename(f)[:-5]
    st=[k for k,v in d.get('stack',{}).items() if v and k!='webgpu']
    a={k:len(v) for k,v in (d.get('assets') or {}).items() if v}
    tg=[]
    if a.get('models'): tg.append('3D')
    if a.get('compressedTextures'): tg.append('KTX2')
    if a.get('hdrEnv'): tg.append('HDR')
    if a.get('video'): tg.append('video')
    if a.get('audio'): tg.append('audio')
    if d.get('canvasCount'): tg.append(f"canvas×{d['canvasCount']}")
    rows.append((t.get(s,''),(d.get('title') or s)[:34],', '.join(st) or '—',', '.join(tg) or '—'))
import datetime
hdr=[f"# Corpus — Awwwards SOTD, harvested {datetime.date.today()}","",
 f"{len(rows)} sites rendered headless (1440×900), scrolled, network + runtime captured",
 "via `scripts/site-inspect.mjs`. Regenerate with `scripts/harvest.sh`.","",
 "| Site | Stack (globals) | Evidence |","|---|---|---|"]
hdr+= [f"| [{ti}]({u}) | {st} | {tg} |" for u,ti,st,tg in rows]
hdr+=["","## Reading this table","",
 "`Stack (globals)` is **under-reported by design** — bundlers hide library globals.",
 "A row showing `—` with `3D, KTX2, HDR` is a heavy three.js site. Trust Evidence."]
open(f'{SKILL}/references/corpus.md','w').write('\n'.join(hdr)+'\n')
print(f"      corpus.md: {len(rows)} sites")
PY
echo "done."
