"""Genera un preview por cada personaje del banco para comparar."""
from pathlib import Path
from compose_cover import compose, PERSONAJES, TEMP, OUTPUT, IMG_EXTS

if __name__ == "__main__":
    chars = sorted(p for p in PERSONAJES.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS)
    for ch in chars:
        out = OUTPUT / f"preview_{ch.stem}.png"
        compose(
            cover_path=TEMP / "song.jpg",
            title="MONTAGEM ALQUIMIA (SLOWED)",
            artist="h6itam",
            character_path=ch,
            out_path=out,
        )
        print(f"OK -> {out.name}")
