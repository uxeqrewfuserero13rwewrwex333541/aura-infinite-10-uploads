"""Genera previews variando personaje e icono para verlos todos."""
from pathlib import Path
from compose_cover import compose, PERSONAJES, ICONOS, TEMP, OUTPUT, IMG_EXTS

if __name__ == "__main__":
    chars = sorted(p for p in PERSONAJES.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS)
    icons = sorted(p for p in ICONOS.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXTS)
    # Hacer un preview por personaje, rotando el icono para variar.
    for i, ch in enumerate(chars):
        ic = icons[i % len(icons)]
        out = OUTPUT / f"combo_{ch.stem}__{ic.stem}.png"
        compose(
            cover_path=TEMP / "current" / "song.jpg" if (TEMP / "current" / "song.jpg").exists() else TEMP / "song.jpg",
            title="MONTAGEM ALQUIMIA (SLOWED)",
            artist="h6itam",
            character_path=ch,
            icon_path=ic,
            out_path=out,
        )
        print(f"OK -> {out.name}")
