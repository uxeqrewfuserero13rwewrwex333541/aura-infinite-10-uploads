"""Genera 3 portadas distintas para comparar combinaciones random."""
from pathlib import Path
import sys, os
sys.path.insert(0, str(Path(__file__).parent))
from compose_cover import compose, TEMP, OUTPUT

cover = TEMP / "current" / "song.jpg"
if not cover.exists():
    cover = TEMP / "song.jpg"
title = "MONTAGEM ALQUIMIA (SLOWED)"

for i in (1, 2, 3):
    out = OUTPUT / f"preview_combo_{i}.png"
    compose(cover_path=cover, title=title, artist="",
            out_path=out, seed=i * 7)
    print(f"OK -> {out.name}")
