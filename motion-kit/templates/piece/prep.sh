#!/bin/bash
# prep.sh — rebuild every asset this piece uses. One command per asset, so the piece can be rebuilt from source.
set -euo pipefail
cd "$(dirname "$0")"
KIT="${MK_KIT:-$(cd ../.. 2>/dev/null && pwd -P)}"     # point MK_KIT at motion-kit if the piece lives elsewhere
# python3 "$KIT/../vision-lift/subject.py" photos/hero.jpg --out assets/hero
# python3 "$KIT/scripts/wordfit.py" assets/hero-subject.png "WORD."
# python3 "$KIT/../beatsync/beatgrid.py" music/track.wav -o music --click
