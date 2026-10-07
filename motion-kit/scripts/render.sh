#!/bin/bash
# render.sh <piece-dir> [final|draft] — the motion-kit pipeline, end to end.
#   lint → cues + text (cues.py) → sound (sfx.py, cue-driven) → render (final: 240 fps → 180° motion blur
#   at 30 fps; draft: 30 fps, no blur) → mux at the brand loudness → qa.py gate + contact sheet → beatcheck.
#   Output: <piece>/renders/<slug>.mp4 (+ -sheet.jpg). Final ≈ 2.5 min per 20 s on an M-series Mac; draft ≈ 1 min.
# macOS /bin/bash is 3.2: no ${VAR^^}, no mapfile.
set -euo pipefail
P="$(cd "${1:?usage: render.sh <piece-dir> [final|draft]}" && pwd)"; MODE="${2:-final}"
SK="$(cd "$(dirname "$0")/.." && pwd -P)"; SLUG="$(basename "$P")"
BEATSYNC="$(cd "$SK/../beatsync" 2>/dev/null && pwd -P || true)"
PY="${MK_PYTHON:-python3}"
cd "$P"; mkdir -p renders assets/kit
export HYPERFRAMES_SKIP_SKILLS=1
# gsap ships via npm (the kit vendors nothing it can't redistribute); installed once next to the kit
[ -f "$SK/node_modules/gsap/dist/gsap.min.js" ] || (cd "$SK" && npm install --silent --no-audit --no-fund)
# the kit is COPIED into the piece: the renderer serves the piece dir, and symlinks out of it are not safe
cp "$SK"/kit/{mk.css,mk.js,grain.png} "$SK"/kit/fonts/Inter-variable.ttf "$SK/node_modules/gsap/dist/gsap.min.js" assets/kit/
echo "── lint"; npx --yes hyperframes@latest lint 2>&1 | tail -3
npx --yes hyperframes@latest lint 2>&1 | grep -q "0 error" || { echo "lint errors — fix before rendering"; exit 1; }
echo "── cues + text"; "$PY" "$SK/scripts/cues.py" . --out renders/cues.json --text renders/text.json
PULSE=$("$PY" -c "import json;print(json.load(open('renders/cues.json')).get('pulse','') or '')")
# music: MK.finish(tl, {music:{file,start,grid,fade:[a,b]}, cuts:[reel beats]}) → mixed + effects normalized to it
MUSIC_ARGS=$("$PY" -c "
import json;m=json.load(open('renders/cues.json')).get('music') or {}
print(f\"--music {m['file']} --music-start {m.get('start',0)} --fade {m['fade'][0]}:{m['fade'][1]} --report\" if m.get('file') else '')")
echo "── sound ${MUSIC_ARGS:+(music + normalized effects)}"
"$PY" "$SK/scripts/sfx.py" renders/cues.json renders/sfx.wav ${PULSE:+--pulse $PULSE} $MUSIC_ARGS
if [ "$MODE" = draft ]; then
  echo "── render (draft, 30 fps)"
  npx --yes hyperframes@latest render -q draft -f 30 -o renders/v-mb.mp4 2>&1 | grep -E "rendered in|rror" || true
else
  echo "── render (240 fps → motion blur)"
  npx --yes hyperframes@latest render -q looks -f 240 -o renders/v-240.mp4 2>&1 | grep -E "rendered in|rror" || true
  # HyperFrames has no motion blur: average 4 of every 8 frames at 240 fps = a 180° shutter at 30 fps.
  # (2-of-4 at 120 fps DOUBLE-PRINTS fast movers: a label sliding 40 px/frame printed twice.)
  ffmpeg -hide_banner -loglevel error -y -i renders/v-240.mp4 \
    -vf "tmix=frames=4:weights='1 1 1 1',select='not(mod(n\,8))',setpts=N/(30*TB)" -r 30 \
    -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p renders/v-mb.mp4
fi
LUFS=$("$PY" -c "import json,os;b=json.load(open('brand.json' if os.path.exists('brand.json') else '$SK/brand.json'));print(b.get('loudness',{}).get('lufs',-14))")
echo "── mux (two-pass loudnorm → $LUFS LUFS; one pass undershoots sparse mixes)"
M=$(ffmpeg -hide_banner -nostats -i renders/sfx.wav -af "loudnorm=I=$LUFS:TP=-1.5:LRA=20:print_format=json" -f null - 2>&1 | \
  "$PY" -c "import sys,json,re;d=json.loads(re.search(r'\{[^{}]*\}',sys.stdin.read(),re.S).group(0));print(':'.join(f'{k}={d[v]}' for k,v in [('measured_I','input_i'),('measured_TP','input_tp'),('measured_LRA','input_lra'),('measured_thresh','input_thresh'),('offset','target_offset')]))")
ffmpeg -hide_banner -loglevel error -y -i renders/v-mb.mp4 -i renders/sfx.wav -map 0:v -map 1:a \
  -af "loudnorm=I=$LUFS:TP=-1.5:LRA=20:$M:linear=true" -c:v copy -c:a aac -b:a 192k -ar 48000 -shortest -movflags +faststart \
  -map_metadata -1 "renders/$SLUG.mp4"
CANON=""; [ -f COPY.md ] && CANON="--canon COPY.md"
echo "── qa"; "$PY" "$SK/scripts/qa.py" . "renders/$SLUG.mp4" $CANON
# on the beat: every planned cut within 50 ms of a detected song beat (../beatsync)
CUTS=$("$PY" -c "import json;d=json.load(open('renders/cues.json'));print(','.join(str(c) for c in d.get('cuts',[])))")
GRID=$("$PY" -c "import json;print((json.load(open('renders/cues.json')).get('music') or {}).get('grid',''))")
if [ -n "$CUTS" ] && [ -n "$GRID" ]; then
  [ -n "$BEATSYNC" ] || { echo "beatsync not found next to motion-kit: cannot prove the cuts are on the beat"; exit 1; }
  echo "── beatcheck"; "$PY" "$BEATSYNC/beatcheck.py" "renders/$SLUG.mp4" --grid "$GRID" --cuts "$CUTS"
fi
