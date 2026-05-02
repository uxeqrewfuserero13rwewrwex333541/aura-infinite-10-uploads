"""Preview con fondo blanco - dos variantes:
   1. crudo: pega las imagenes tal cual (van a quedar rectangulos negros)
   2. limpio: hace transparente el fondo oscuro on-the-fly antes de pegar
"""
from collections import deque
from pathlib import Path
from PIL import Image
import compose_cover as cc


def darks_to_transparent(img: Image.Image, threshold: int = 25) -> Image.Image:
    """Flood fill desde los bordes: pixeles oscuros conectados al borde -> alpha 0."""
    img = img.convert("RGBA")
    w, h = img.size
    px = img.load()
    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def is_bg(x, y):
        r, g, b, _a = px[x, y]
        return max(r, g, b) <= threshold

    for x in range(w):
        for y in (0, h - 1):
            if not visited[y * w + x] and is_bg(x, y):
                q.append((x, y)); visited[y * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            if not visited[y * w + x] and is_bg(x, y):
                q.append((x, y)); visited[y * w + x] = 1

    while q:
        x, y = q.popleft()
        r, g, b, _a = px[x, y]
        px[x, y] = (r, g, b, 0)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if not visited[idx] and is_bg(nx, ny):
                    visited[idx] = 1
                    q.append((nx, ny))
    return img


def preprocess_folder(folder: Path, out_folder: Path) -> None:
    """Genera version 'limpia' de cada imagen para uso temporal."""
    out_folder.mkdir(parents=True, exist_ok=True)
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in cc.IMG_EXTS:
            continue
        img = Image.open(f)
        clean = darks_to_transparent(img)
        clean.save(out_folder / (f.stem + ".png"))


if __name__ == "__main__":
    cover = cc.TEMP / "current" / "song.jpg"
    if not cover.exists():
        cover = cc.TEMP / "song.jpg"
    title = "MONTAGEM ALQUIMIA (SLOWED)"
    artist = "h6itam"

    # Version 1: cruda con fondo blanco
    cc.compose(cover_path=cover, title=title, artist=artist,
               out_path=cc.OUTPUT / "WHITE_crudo.png",
               bg="white", seed=1)
    print("OK -> WHITE_crudo.png")

    # Version 2: limpia (procesa los negros a transparente primero)
    tmp_pers = cc.ROOT / "temp" / "_clean_personajes"
    tmp_icon = cc.ROOT / "temp" / "_clean_iconos"
    preprocess_folder(cc.PERSONAJES, tmp_pers)
    preprocess_folder(cc.ICONOS, tmp_icon)

    pers_clean = sorted(tmp_pers.glob("*.png"))[0]
    icon_clean = sorted(tmp_icon.glob("*.png"))[0]
    cc.compose(cover_path=cover, title=title, artist=artist,
               character_path=pers_clean, icon_path=icon_clean,
               out_path=cc.OUTPUT / "WHITE_limpio.png",
               bg="white")
    print("OK -> WHITE_limpio.png")
