"""
Genera el elemento del CENTRO de la portada segun un estilo.

Estilos:
  - "vinyl":  Vinilo realista con la portada como label central (default).
  - "laptop": MacBook con la portada en la pantalla (requiere assets/centros/laptop.png).

Devuelve un Image RGBA listo para pegar/superponer. La de vinyl tiene tamano
cuadrado (apto para rotar sin deformar con FFmpeg).
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "centros"

# Coords de la pantalla del laptop (si existe assets/centros/laptop.png)
LAPTOP_SCREEN_REL = (0.170, 0.041, 0.837, 0.598)
# Diametro del label central del vinilo, como fraccion del lado del vinilo.
# El hueco real del vinilo actual mide ~48%; usamos 0.52 para que la portada
# lo llene SIN que se note un anillo entre la portada y el borde interior.
# Si subis demasiado este valor, la portada empieza a tapar parte del vinilo.
VINYL_HOLE_RATIO = 0.52


def fit_cover_square(cover: Image.Image, size: int) -> Image.Image:
    """Recorta la portada al cuadrado central y la escala al tamano dado."""
    cover = cover.convert("RGBA")
    cw, ch = cover.size
    side = min(cw, ch)
    cover = cover.crop(((cw - side) // 2, (ch - side) // 2,
                        (cw + side) // 2, (ch + side) // 2))
    return cover.resize((size, size), Image.LANCZOS)


def fit_cover_169(cover: Image.Image, w: int, h: int) -> Image.Image:
    """Recorta la portada al aspect ratio del box (rellena, no deja bandas)."""
    cover = cover.convert("RGBA")
    cw, ch = cover.size
    target = w / h
    src = cw / ch
    if src > target:
        new_w = int(ch * target)
        cover = cover.crop(((cw - new_w) // 2, 0, (cw + new_w) // 2, ch))
    else:
        new_h = int(cw / target)
        cover = cover.crop((0, (ch - new_h) // 2, cw, (ch + new_h) // 2))
    return cover.resize((w, h), Image.LANCZOS)


def make_laptop_center(cover: Image.Image, target_h: int = 460) -> Image.Image:
    """Devuelve la imagen del laptop con la portada incrustada en su pantalla.
    Escala todo el laptop para que su altura sea target_h.
    """
    laptop = Image.open(ASSETS / "laptop.png").convert("RGBA")
    lw, lh = laptop.size
    # Coordenadas de la pantalla en el PNG original
    x0 = int(lw * LAPTOP_SCREEN_REL[0])
    y0 = int(lh * LAPTOP_SCREEN_REL[1])
    x1 = int(lw * LAPTOP_SCREEN_REL[2])
    y1 = int(lh * LAPTOP_SCREEN_REL[3])
    sw, sh = x1 - x0, y1 - y0

    # Encajar la portada en la pantalla
    cover_screen = fit_cover_169(cover, sw, sh)
    laptop.paste(cover_screen, (x0, y0), cover_screen)

    # Escalar todo el laptop para que la altura final sea target_h
    scale = target_h / lh
    new_w = int(lw * scale)
    new_h = int(lh * scale)
    return laptop.resize((new_w, new_h), Image.LANCZOS)


def make_vinyl_center(cover: Image.Image, size: int = 500) -> Image.Image:
    """Devuelve el vinilo realista con la portada llenando todo el hueco central.
    El resultado es CUADRADO (apto para rotar con FFmpeg sin recortes).
    """
    vinyl = Image.open(ASSETS / "vinilo.png").convert("RGBA")
    vw, vh = vinyl.size
    side = min(vw, vh)
    vinyl = vinyl.crop(((vw - side) // 2, (vh - side) // 2,
                        (vw + side) // 2, (vh + side) // 2))
    vinyl = vinyl.resize((size, size), Image.LANCZOS)

    # Label = portada llenando todo el hueco circular del vinilo
    label_size = int(size * VINYL_HOLE_RATIO)
    label_sq = fit_cover_square(cover, label_size)
    mask = Image.new("L", (label_size, label_size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, label_size, label_size), fill=255)
    label = Image.new("RGBA", (label_size, label_size), (0, 0, 0, 0))
    label.paste(label_sq, (0, 0), mask)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(vinyl)
    off = (size - label_size) // 2
    out.alpha_composite(label, (off, off))

    # Agujero central pequeño (centro del disco)
    hole = max(4, int(size * 0.012))
    ImageDraw.Draw(out).ellipse(
        (size // 2 - hole, size // 2 - hole, size // 2 + hole, size // 2 + hole),
        fill=(0, 0, 0, 255)
    )
    return out


def make_center(style: str, cover: Image.Image, size: int = 500) -> Image.Image:
    """Devuelve la imagen del centro segun el estilo.
    style en {"laptop", "vinyl"}. size es referencia (alto para laptop, lado para vinilo).
    """
    if style == "laptop":
        if not (ASSETS / "laptop.png").exists():
            raise FileNotFoundError(
                "Estilo 'laptop' requiere assets/centros/laptop.png (no encontrado)."
            )
        return make_laptop_center(cover, target_h=size)
    elif style == "vinyl":
        return make_vinyl_center(cover, size=size)
    else:
        raise ValueError(f"Estilo desconocido: {style!r}")


# Solo 'vinyl' por defecto (el laptop fue removido por el usuario).
# Si en el futuro volves a poner assets/centros/laptop.png, descomenta:
# CENTER_STYLES = ("vinyl", "laptop")
CENTER_STYLES = ("vinyl",)
