"""
Compone la portada estatica 1920x1080 para los videos del canal.
Layout: fondo negro + 3 elementos en linea horizontal
  izquierda: personaje con aura
  centro:    portada de la cancion como disco/vinilo
  derecha:   icono musical (airpods/headphones/dj/...)
debajo: titulo de la cancion + artista
"""
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from compose_center import make_center, CENTER_STYLES

ROOT = Path(__file__).resolve().parent.parent
TEMP = ROOT / "temp"
ASSETS = ROOT / "assets"
OUTPUT = ROOT / "output"
PERSONAJES = ROOT / "personajes"
PERSONAJES_IZQ = PERSONAJES / "izquierda"
PERSONAJES_DER = PERSONAJES / "derecha"
LOGO_PATH = ROOT / "assets" / "logo_canal.png"
SPECTRUM_PATH = ROOT / "assets" / "spectrum.png"

W, H = 1920, 1080
# Fuente del repo (funciona igual en macOS local y Ubuntu en GitHub Actions).
# Inter Bold, libre, similar a Avenir Next Heavy pero portable.
FONT_PATH = str(ROOT / "assets" / "fonts" / "Inter-Bold.ttf")
# Marca de agua del canal: tamano y margen
LOGO_HEIGHT = 60      # alto en pixels (chico)
LOGO_MARGIN = 40      # margen desde el borde
LOGO_OPACITY = 180    # 0-255 (un poco translucido para que sea sutil)
# Espectros a los lados del titulo
SPECTRUM_HEIGHT = 70  # alto del espectro (pixels)
SPECTRUM_GAP = 30     # separacion entre espectro y titulo
BG_BLACK = (0, 0, 0)
BG_WHITE = (255, 255, 255)
BG = BG_BLACK
TEXT_COLOR = (255, 255, 255)


def auto_crop(img: Image.Image, tolerance: int = 25) -> Image.Image:
    """Recorta la imagen al bounding box del contenido real.
    Detecta automaticamente el color del fondo a partir de las 4 esquinas:
    - Si la imagen es RGBA con transparencia significativa: usa el canal alpha.
    - Si no: usa el color promedio de las esquinas como referencia y considera
      "contenido" cualquier pixel que difiera del fondo en mas de `tolerance`.
    Devuelve la imagen recortada (RGBA).
    """
    img = img.convert("RGBA")
    a = img.split()[-1]
    if a.getextrema()[0] < 255:
        bbox = a.getbbox()
    else:
        w, h = img.size
        rgb = img.convert("RGB")
        # Promedio del color de las 4 esquinas (asumimos que son fondo)
        corners = [rgb.getpixel((0, 0)), rgb.getpixel((w - 1, 0)),
                   rgb.getpixel((0, h - 1)), rgb.getpixel((w - 1, h - 1))]
        bg_r = sum(c[0] for c in corners) // 4
        bg_g = sum(c[1] for c in corners) // 4
        bg_b = sum(c[2] for c in corners) // 4
        # Mascara: contenido = pixels cuya distancia al color de fondo > tolerance
        gray = Image.eval(rgb, lambda v: v)  # noop, just to convert
        mask = Image.new("L", (w, h), 0)
        mp = mask.load()
        rp = rgb.load()
        for y in range(h):
            for x in range(w):
                r, g, b = rp[x, y]
                if abs(r - bg_r) > tolerance or abs(g - bg_g) > tolerance or abs(b - bg_b) > tolerance:
                    mp[x, y] = 255
        bbox = mask.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def fit_into_box(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Auto-recorta al contenido real y escala para caber en el box."""
    img = auto_crop(img)
    img.thumbnail((box_w, box_h), Image.LANCZOS)
    return img


def make_vinyl(cover: Image.Image, size: int) -> Image.Image:
    """Convierte una imagen cuadrada en un disco/vinilo con label central."""
    # vinilo negro circular
    vinyl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(vinyl)
    # cuerpo del disco (negro brillante)
    draw.ellipse((0, 0, size, size), fill=(15, 15, 15, 255))
    # surcos sutiles
    for r in range(int(size * 0.18), int(size * 0.48), 6):
        draw.ellipse(
            (size // 2 - r, size // 2 - r, size // 2 + r, size // 2 + r),
            outline=(40, 40, 40, 255), width=1
        )
    # label = portada cuadrada recortada en circulo, ~38% del disco
    label_size = int(size * 0.38)
    cover_sq = cover.copy().convert("RGBA")
    # crop a cuadrado
    cw, ch = cover_sq.size
    side = min(cw, ch)
    cover_sq = cover_sq.crop(((cw - side) // 2, (ch - side) // 2,
                              (cw + side) // 2, (ch + side) // 2))
    cover_sq = cover_sq.resize((label_size, label_size), Image.LANCZOS)
    # mascara circular para el label
    label_mask = Image.new("L", (label_size, label_size), 0)
    ImageDraw.Draw(label_mask).ellipse((0, 0, label_size, label_size), fill=255)
    label = Image.new("RGBA", (label_size, label_size), (0, 0, 0, 0))
    label.paste(cover_sq, (0, 0), label_mask)
    # pegar label centrado
    off = (size - label_size) // 2
    vinyl.paste(label, (off, off), label)
    # agujero central
    hole = int(size * 0.025)
    ImageDraw.Draw(vinyl).ellipse(
        (size // 2 - hole, size // 2 - hole, size // 2 + hole, size // 2 + hole),
        fill=(0, 0, 0, 255)
    )
    return vinyl


def make_aura(img: Image.Image, color=(140, 90, 255), intensity: int = 60) -> Image.Image:
    """Agrega un glow/aura alrededor de una imagen con transparencia."""
    img = img.convert("RGBA")
    w, h = img.size
    pad = intensity
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    # aura: silueta de la imagen pintada de color y desenfocada varias veces
    alpha = img.split()[-1]
    silhouette = Image.new("RGBA", img.size, color + (0,))
    silhouette.putalpha(alpha)
    aura = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    aura.paste(silhouette, (pad, pad), silhouette)
    aura = aura.filter(ImageFilter.GaussianBlur(radius=intensity * 0.6))
    # intensificar
    r, g, b, a = aura.split()
    a = a.point(lambda v: min(255, int(v * 1.8)))
    aura = Image.merge("RGBA", (r, g, b, a))
    # pegar imagen original encima
    canvas.alpha_composite(aura)
    canvas.paste(img, (pad, pad), img)
    return canvas


def make_placeholder_character(size: int) -> Image.Image:
    """Personaje placeholder: silueta circular morada con texto."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((0, 0, size, size), fill=(80, 50, 180, 255))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size // 8)
    except OSError:
        font = ImageFont.load_default()
    txt = "PERSONAJE"
    bbox = d.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2, (size - th) / 2), txt, fill=(255, 255, 255), font=font)
    return img


def make_placeholder_icon(size: int) -> Image.Image:
    """Icono placeholder estilo airpods (caja blanca redondeada)."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(size * 0.15)
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size // 6,
                        fill=(245, 245, 245, 255))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size // 9)
    except OSError:
        font = ImageFont.load_default()
    txt = "AIRPODS"
    bbox = d.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2, (size - th) / 2), txt, fill=(60, 60, 60), font=font)
    return img


IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def pick_random(folder: Path) -> Path | None:
    """Elige aleatoriamente una imagen de la carpeta."""
    if not folder.exists():
        return None
    files = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in IMG_EXTS]
    return random.choice(files) if files else None


def pick_two_distinct(folder: Path) -> tuple[Path | None, Path | None]:
    """Elige 2 imagenes distintas al azar (si hay solo 1, devuelve repetida)."""
    if not folder.exists():
        return (None, None)
    files = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in IMG_EXTS]
    if not files:
        return (None, None)
    if len(files) == 1:
        return (files[0], files[0])
    return tuple(random.sample(files, 2))


def pick_pair_from_sides(left_folder: Path, right_folder: Path) -> tuple[Path | None, Path | None]:
    """Elige 1 personaje al azar de cada carpeta (izquierda y derecha).
    Si la misma imagen (mismo nombre) cae en ambos lados, vuelve a tirar para
    el lado derecho hasta que sean distintos.
    """
    izq_files = [p for p in left_folder.iterdir()
                 if p.is_file() and p.suffix.lower() in IMG_EXTS] if left_folder.exists() else []
    der_files = [p for p in right_folder.iterdir()
                 if p.is_file() and p.suffix.lower() in IMG_EXTS] if right_folder.exists() else []
    if not izq_files or not der_files:
        return (None, None)
    izq = random.choice(izq_files)
    # Evitar usar el mismo personaje en ambos lados
    der_candidates = [p for p in der_files if p.name != izq.name] or der_files
    der = random.choice(der_candidates)
    return (izq, der)


def compose(cover_path: Path, title: str, artist: str,
            character_path: Path | None = None,
            icon_path: Path | None = None,
            out_path: Path | None = None,
            seed: int | None = None,
            bg: str = "white",
            center_style: str | None = None,
            skip_center: bool = False) -> Path:
    """Compose la portada estatica.
    Coloca 2 personajes random distintos (uno a izq, otro a der) + centro + titulo.
    center_style: "vinyl" (default; "laptop" requiere assets/centros/laptop.png).
    skip_center: si True, NO pega el centro (util para luego superponer un centro
                 animado con FFmpeg, p.ej. vinilo girando).
    artist: ignorado en la composicion actual (se decidio mostrar solo titulo).
    """
    if seed is not None:
        random.seed(seed)
    # Carpetas: el NOMBRE indica HACIA DONDE MIRA el personaje
    #   personajes/izquierda/ = mira a la izquierda -> se ubica en el lado DERECHO
    #                           del video (asi "mira hacia el centro" = al vinilo)
    #   personajes/derecha/   = mira a la derecha   -> se ubica en el lado IZQUIERDO
    if character_path is None:
        # pick_pair_from_sides devuelve (de_izq, de_der). Los cruzamos:
        mira_izq, mira_der = pick_pair_from_sides(PERSONAJES_IZQ, PERSONAJES_DER)
        char_left_path = mira_der    # "mira a la derecha" -> se pone a la izquierda
        char_right_path = mira_izq   # "mira a la izquierda" -> se pone a la derecha
    else:
        char_left_path = character_path
        char_right_path = icon_path or pick_random(PERSONAJES_DER)
    if center_style is None:
        center_style = "vinyl"  # default actual
    bg_color = BG_WHITE if bg == "white" else BG_BLACK
    text_color = (0, 0, 0) if bg == "white" else (255, 255, 255)
    canvas = Image.new("RGB", (W, H), bg_color)

    # Los 3 elementos (personaje izq, centro, personaje der) caben en un box
    # cuadrado del MISMO tamano. Cambia ELEMENT_SIZE para escalar todo a la vez.
    ELEMENT_SIZE = 500
    cx_left, cx_center, cx_right = int(W * 0.22), W // 2, int(W * 0.78)
    cy = int(H * 0.46)  # un poco arriba del medio para dejar lugar al texto

    # 1) PERSONAJE IZQUIERDA (auto-recortado y ajustado a ELEMENT_SIZE)
    if char_left_path and Path(char_left_path).exists():
        char_l = Image.open(char_left_path).convert("RGBA")
        char_l = fit_into_box(char_l, ELEMENT_SIZE, ELEMENT_SIZE)
    else:
        char_l = make_placeholder_character(ELEMENT_SIZE)
    cw, ch = char_l.size
    canvas.paste(char_l, (cx_left - cw // 2, cy - ch // 2), char_l)

    # 2) CENTRO (vinilo con label = portada). Cuadrado de ELEMENT_SIZE.
    if not skip_center:
        cover = Image.open(cover_path).convert("RGBA")
        center = make_center(center_style, cover, size=ELEMENT_SIZE)
        ccw, cch = center.size
        canvas.paste(center, (cx_center - ccw // 2, cy - cch // 2), center)

    # 3) PERSONAJE DERECHA (auto-recortado y ajustado a ELEMENT_SIZE)
    if char_right_path and Path(char_right_path).exists():
        char_r = Image.open(char_right_path).convert("RGBA")
        char_r = fit_into_box(char_r, ELEMENT_SIZE, ELEMENT_SIZE)
    else:
        char_r = make_placeholder_character(ELEMENT_SIZE)
    iw, ih = char_r.size
    canvas.paste(char_r, (cx_right - iw // 2, cy - ih // 2), char_r)

    # 4) TEXTO debajo - solo el titulo, tipografia Avenir Next Heavy (gordita)
    draw = ImageDraw.Draw(canvas)
    # Avenir Next.ttc indices: 0=Regular, 4=DemiBold, 6=Bold, 8=Heavy.
    # Heavy = el peso mas grueso, similar al "playlist." del ejemplo.
    try:
        font_title = ImageFont.truetype(FONT_PATH, 80)
    except (OSError, IOError):
        font_title = ImageFont.load_default()

    title_y = int(H * 0.86)
    title_bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = title_bbox[2] - title_bbox[0]
    th = title_bbox[3] - title_bbox[1]
    title_x = (W - tw) / 2
    # Borde blanco alrededor del texto (stroke)
    stroke_color = (255, 255, 255) if bg == "black" else (255, 255, 255)
    draw.text((title_x, title_y), title, fill=text_color, font=font_title,
              stroke_width=4, stroke_fill=stroke_color)

    # 4b) ESPECTROS a izq y derecha del titulo
    if SPECTRUM_PATH.exists():
        spec = Image.open(SPECTRUM_PATH).convert("RGBA")
        scale = SPECTRUM_HEIGHT / spec.size[1]
        spec = spec.resize((int(spec.size[0] * scale), SPECTRUM_HEIGHT), Image.LANCZOS)
        sw, sh = spec.size
        # Centrado verticalmente con el texto del titulo
        spec_y = title_y + (th - sh) // 2 + th // 4  # ajuste vertical
        # Izquierda
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.alpha_composite(spec, (int(title_x - SPECTRUM_GAP - sw), spec_y))
        # Derecha (se puede espejar para simetria)
        spec_mirror = spec.transpose(Image.FLIP_LEFT_RIGHT)
        canvas_rgba.alpha_composite(spec_mirror, (int(title_x + tw + SPECTRUM_GAP), spec_y))
        canvas = canvas_rgba.convert("RGB")
        draw = ImageDraw.Draw(canvas)

    # 5) MARCA DE AGUA: logo del canal en esquinas superiores (chiquito)
    if LOGO_PATH.exists():
        logo = Image.open(LOGO_PATH).convert("RGBA")
        # Escalar al alto deseado manteniendo aspecto
        scale = LOGO_HEIGHT / logo.size[1]
        new_size = (int(logo.size[0] * scale), LOGO_HEIGHT)
        logo = logo.resize(new_size, Image.LANCZOS)
        # Aplicar opacidad sutil
        if LOGO_OPACITY < 255:
            r, g, b, a = logo.split()
            a = a.point(lambda v: int(v * LOGO_OPACITY / 255))
            logo = Image.merge("RGBA", (r, g, b, a))
        # Pegar en esquinas superiores izquierda y derecha
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.alpha_composite(logo, (LOGO_MARGIN, LOGO_MARGIN))
        canvas_rgba.alpha_composite(
            logo, (W - logo.size[0] - LOGO_MARGIN, LOGO_MARGIN)
        )
        canvas = canvas_rgba.convert("RGB")

    out_path = out_path or OUTPUT / "cover_preview.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    out = compose(
        cover_path=TEMP / "song.jpg",
        title="MONTAGEM ALQUIMIA (SLOWED)",
        artist="h6itam",
        seed=1,  # determinista para preview
    )
    print(f"OK -> {out}")
