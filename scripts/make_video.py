"""
Pipeline end-to-end: dado un link de YouTube genera:
  - <slug>.mp4    -> video horizontal 1920x1080 con la portada estatica + audio
  - <slug>.txt    -> titulo, descripcion y tags listos para copiar al subir

Uso:
    python make_video.py <youtube_url> [--keep-temp]
"""
from __future__ import annotations
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image
from imageio_ffmpeg import get_ffmpeg_exe

from compose_cover import compose, TEMP, OUTPUT, W, H
from compose_center import make_vinyl_center, CENTER_STYLES
from drive_upload import upload_video_to_drive
from youtube_upload import upload_video_to_youtube, post_comment
from musicbrainz_lookup import lookup_song, parse_youtube_auto_description
from radial_visualizer import render_radial_video, VINYL_SIZE

ROOT = Path(__file__).resolve().parent.parent
VENV_BIN = ROOT / "venv" / "bin"
# Buscar yt-dlp: primero en venv local, sino en PATH global (GitHub Actions usa pip global)
_VENV_YTDLP = VENV_BIN / "yt-dlp"
YT_DLP = str(_VENV_YTDLP) if _VENV_YTDLP.exists() else (shutil.which("yt-dlp") or "yt-dlp")
FFMPEG = get_ffmpeg_exe()


def slugify(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:max_len].strip("_") or "video"


def fetch_metadata_and_assets(url: str, work_dir: Path) -> dict:
    """Descarga audio mp3 + thumbnail jpg y devuelve metadata."""
    work_dir.mkdir(parents=True, exist_ok=True)
    # 1) metadata JSON
    meta_proc = subprocess.run(
        [YT_DLP, "--dump-single-json", "--no-warnings", url],
        capture_output=True, text=True, check=True,
    )
    meta = json.loads(meta_proc.stdout)
    # 2) audio + thumbnail
    subprocess.run([
        YT_DLP,
        "--ffmpeg-location", FFMPEG,
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-o", str(work_dir / "song.%(ext)s"),
        url,
    ], check=True)
    return meta


def make_video(image_path: Path, audio_path: Path, out_path: Path) -> None:
    """Combina imagen estatica + audio en un mp4 1920x1080."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def make_video_with_spinning_vinyl(base_path: Path, vinyl_path: Path,
                                   audio_path: Path, out_path: Path,
                                   overlay_x: int, overlay_y: int,
                                   seconds_per_turn: float = 4.0) -> None:
    """Combina:
       - base.png   (lienzo 1920x1080 sin centro)
       - vinyl.png  (vinilo cuadrado con la portada en el label)
       - audio mp3
       Renderiza un mp4 con el vinilo rotando sobre la base.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 2*PI radianes = 1 vuelta. Velocidad angular = 2*PI / seconds_per_turn rad/s.
    omega = 2 * 3.141592653589793 / seconds_per_turn
    rotate_filter = (
        f"[1:v]format=rgba,rotate={omega}*t:c=#00000000:ow=iw:oh=ih[spin];"
        f"[0:v][spin]overlay={overlay_x}:{overlay_y}:format=auto"
    )
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", str(base_path),
        "-loop", "1", "-i", str(vinyl_path),
        "-i", str(audio_path),
        "-filter_complex", rotate_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def detect_genre_keywords(title: str) -> list[str]:
    """Detect subgenre from title. Returns a list of related tags."""
    t = title.lower()
    extra: list[str] = []
    if any(w in t for w in ("phonk", "drift")):
        extra += ["phonk", "drift phonk", "phonk music", "tiktok phonk", "aggressive phonk"]
    if any(w in t for w in ("montagem", "funk", "brasileiro", "brazilian")):
        extra += ["brazilian funk", "funk brasileiro", "montagem", "funk tiktok",
                  "baile funk", "mtg"]
    if "hardstyle" in t:
        extra += ["hardstyle", "hardstyle remix"]
    if "hardtekk" in t or "hardtek" in t:
        extra += ["hardtekk", "hardtek"]
    if "hoodtrap" in t or "hood trap" in t:
        extra += ["hoodtrap", "hood trap"]
    if "jumpstyle" in t:
        extra += ["jumpstyle"]
    if "slowed" in t or "reverb" in t:
        extra += ["slowed", "slowed reverb", "slowed and reverb", "slowed song"]
    if "sped up" in t or "speed up" in t or "spedup" in t:
        extra += ["sped up", "sped up audio", "fast version", "tiktok sped up"]
    if "remix" in t:
        extra += ["remix", "viral remix"]
    if any(w in t for w in ("8d", "audio", "edit")):
        extra += ["audio edit", "8d audio", "music edit"]
    return extra


def build_youtube_metadata(meta: dict, artists: list[str] | None = None,
                           label: str | None = None) -> str:
    """Generate title / description / tags optimized for the YouTube algorithm.

    Best practices applied:
    - Title <= 95 chars with primary keyword first
    - Description 200+ words with keyword in the FIRST line (above-the-fold)
    - Hashtags at the end (10)
    - Genre-specific tags (no generic spam)

    artists: list of artists (e.g. ["Rubikdice", "MC X"]). If None, uses uploader.
    label: record label name. If None, defaults to "Independent".
    """
    raw_title = meta.get("title", "Untitled")
    uploader = meta.get("uploader", "") or ""

    title = raw_title.strip()
    if len(title) > 95:
        title = title[:92].rstrip() + "..."

    if artists is None or not artists:
        artists = [uploader] if uploader else ["Various Artists"]
    artists_str = ", ".join(artists)
    if not label:
        label = "Independent"

    # ----- DESCRIPTION optimized for SEO (200+ words, in English) -----
    first_line = f"🎵 {title} | Aura Infinite 10"

    genre_extra = detect_genre_keywords(title)
    genre_blurb = (
        " One of the viral songs of the moment."
        if not genre_extra else
        f" {' / '.join(genre_extra[:3]).title()} going viral right now."
    )

    description = f"""{first_line}

🔥 Enjoy {title} on Aura Infinite 10.{genre_blurb}
Subscribe and turn on 🔔 notifications so you don't miss any viral song.

🎤 Artists: {artists_str}
🏷️ Label: {label}

If you liked it, drop a 👍, comment your favorite song and share it with your friends.
On this YouTube channel we upload the best viral songs from TikTok, Reels and Instagram every day.
If you want us to upload a specific song, leave it in the comments.

✅ A new hit every day
✅ The most viral songs of the moment
✅ Best beats of phonk, Brazilian funk, hardstyle, hardtekk, hoodtrap and jumpstyle

────────────────────────
🔗 More videos: https://www.youtube.com/@aurainfinite10
────────────────────────

#viral #music #fyp #tiktok #trending #foryou #viralmusic #phonk #brazilianfunk #hardstyle

⚠️ DISCLAIMER: All rights belong to their respective owners. No copyright infringement intended. If you are the owner and want this content removed or credited, please contact the channel."""

    # ----- TAGS -----
    title_tokens = [t.lower() for t in re.findall(r"\w+", raw_title)
                    if len(t) > 2 and t.lower() not in {"the", "and", "feat", "ft"}]
    base_tags = [
        "viral music", "viral", "tiktok", "fyp", "for you",
        "trending music", "viral song 2026", "trending",
        "viral songs", "viral hits",
    ]
    tags = list(dict.fromkeys(title_tokens + genre_extra + base_tags))
    for a in artists:
        if a and a.lower() not in tags:
            tags.append(a.lower())
    tags = tags[:25]

    return (
        f"=== TITULO ===\n{title}\n\n"
        f"=== DESCRIPCION ===\n{description}\n\n"
        f"=== TAGS ===\n{', '.join(tags)}\n"
    )


# Coordenadas donde se pega el centro en el lienzo (deben coincidir con compose_cover.py)
CENTER_SIZE = 500  # tamaño cuadrado del vinilo
CX_CENTER = W // 2
CY_CENTER = int(H * 0.46)
OVERLAY_X = CX_CENTER - CENTER_SIZE // 2
OVERLAY_Y = CY_CENTER - CENTER_SIZE // 2


def prompt_artists_and_label(title: str, uploader: str,
                             yt_description: str = "") -> tuple[list[str], str]:
    """Antes de generar la metadata, pide al usuario que confirme artistas + label.
    Sugiere primero lo que parsea de la descripcion auto-generada de YouTube
    ('Provided to YouTube by ...'), si no encuentra cae a MusicBrainz.
    """
    print()
    print("=== METADATA: artistas y label ===")
    print(f"Titulo: {title}")
    print(f"Uploader del video original: {uploader}")

    # 1) Intentar primero con la descripcion auto-generada de YouTube
    yt_parsed = parse_youtube_auto_description(yt_description)
    if yt_parsed["matched"]:
        suggested_artists = yt_parsed["artists"]
        suggested_label = yt_parsed["label"] or "Independent"
        print(f"  YouTube auto-desc dice: artistas={suggested_artists}, label={suggested_label}")
    else:
        # 2) Fallback a MusicBrainz
        print("  YouTube auto-desc no encontrada. Buscando en MusicBrainz...")
        mb = lookup_song(title)
        suggested_artists = mb["artists"] if mb["matched"] else ([uploader] if uploader else [])
        suggested_label = mb["label"] or "Independent"
        if mb["matched"]:
            print(f"  MusicBrainz dice: artistas={suggested_artists}, label={suggested_label}")
        else:
            print(f"  MusicBrainz tampoco encontro. Default: artista={uploader}")
    print()
    artists_input = input(
        f"Artistas (Enter = '{', '.join(suggested_artists)}', "
        f"o escribi separados por coma): "
    ).strip()
    if artists_input:
        artists = [a.strip() for a in artists_input.split(",") if a.strip()]
    else:
        artists = suggested_artists or ["Various Artists"]

    label_input = input(f"Label (Enter = '{suggested_label}'): ").strip()
    label = label_input if label_input else suggested_label

    print(f"=> Artistas finales: {artists}")
    print(f"=> Label final: {label}")
    print()
    return artists, label


def run(url: str, keep_temp: bool = False, force_style: str | None = None,
        bg: str = "white", upload: bool = True,
        publish_date: str | None = None,
        artists: list[str] | None = None,
        label: str | None = None,
        skip_prompt: bool = False) -> None:
    work = TEMP / "current"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    print(f"[1/5] Descargando audio + thumbnail de {url}")
    meta = fetch_metadata_and_assets(url, work)
    title = meta.get("title", "video")
    artist = meta.get("uploader", "")
    slug = slugify(title)

    audio_path = work / "song.mp3"
    cover_src = work / "song.jpg"
    if not audio_path.exists() or not cover_src.exists():
        print("ERROR: no se descargaron audio o thumbnail", file=sys.stderr)
        sys.exit(1)

    style = force_style or random.choice(CENTER_STYLES)
    print(f"[2/5] Estilo del centro: {style.upper()}")

    # COVER (thumbnail) = portada estatica completa con vinilo
    print("[3/5] Componiendo portada estatica (para thumbnail)")
    cover_png_for_thumb = OUTPUT / f"{slug}_cover.png"
    compose(cover_path=cover_src, title=title, artist=artist,
            out_path=cover_png_for_thumb, center_style=style, bg=bg)

    # VIDEO = base SIN vinilo + visualizador radial + vinilo pulsando + audio
    print("[4/5] Renderizando video con visualizador radial (puede tardar varios minutos)")
    base_no_center = OUTPUT / f"{slug}_base.png"
    compose(cover_path=cover_src, title=title, artist=artist,
            out_path=base_no_center, center_style=style, bg=bg, skip_center=True)
    vinyl_img = make_vinyl_center(Image.open(cover_src), size=VINYL_SIZE)
    video_path = OUTPUT / f"{slug}.mp4"
    render_radial_video(base_no_center, vinyl_img, audio_path, video_path)
    base_no_center.unlink(missing_ok=True)

    print(f"[5/5] Generando metadata YouTube")
    # Si no vinieron artists/label por CLI, preguntar interactivamente (salvo skip_prompt)
    yt_desc = meta.get("description", "") or ""
    if artists is None and not skip_prompt:
        artists, label = prompt_artists_and_label(title, artist, yt_desc)
    elif artists is None:
        # skip_prompt: usar parser de YouTube auto-desc directamente
        parsed = parse_youtube_auto_description(yt_desc)
        if parsed["matched"]:
            artists = parsed["artists"]
            if label is None:
                label = parsed["label"] or "Independent"
        else:
            artists = [artist] if artist else ["Various Artists"]
            if label is None:
                label = "Independent"
    meta_path = OUTPUT / f"{slug}.txt"
    meta_path.write_text(
        build_youtube_metadata(meta, artists=artists, label=label),
        encoding="utf-8",
    )

    if not keep_temp:
        shutil.rmtree(work, ignore_errors=True)

    print()
    print("LISTO. Archivos generados en output/:")
    print(f"  - {video_path.name}")
    print(f"  - {cover_png_for_thumb.name}")
    print(f"  - {meta_path.name}")
    print(f"  Estilo: {style}")

    if upload:
        upload_results(video_path, cover_png_for_thumb, meta_path, slug,
                       publish_date=publish_date)


def upload_results(video_path: Path, cover_path: Path, meta_path: Path, slug: str,
                   publish_date: str | None = None) -> None:
    """Sube a Drive + YouTube. Si Drive OK, borra los archivos locales."""
    print()
    print("=== SUBIDA A LA NUBE ===")

    # 1) DRIVE (lo primero: si esta OK, podemos borrar local despues)
    drive_ok = False
    drive_link = None
    try:
        print("[Drive] Subiendo archivos...")
        drive_info = upload_video_to_drive(video_path, cover_path, meta_path, slug)
        drive_ok = True
        drive_link = drive_info["folder_link"]
        print(f"[Drive] OK - carpeta: {drive_info['folder_name']}")
        print(f"        link: {drive_link}")
    except Exception as e:
        print(f"[Drive] ERROR: {e}")

    # 2) YOUTUBE (subida grande, programada para 12hs)
    yt_ok = False
    yt_url = None
    yt_video_id = None
    try:
        print("[YouTube] Subiendo video (puede tardar varios minutos)...")
        yt_info = upload_video_to_youtube(video_path, cover_path, meta_path,
                                          publish_date=publish_date)
        yt_ok = True
        yt_url = yt_info["url"]
        yt_video_id = yt_info["video_id"]
        print(f"[YouTube] OK - se publica el {yt_info['publish_at']} UTC")
        print(f"          URL: {yt_url}")
        print(f"          Studio: {yt_info['studio_url']}")
        if not yt_info["thumbnail_uploaded"]:
            print(f"          [!] Thumbnail no subido: {yt_info['thumbnail_error']}")
    except Exception as e:
        print(f"[YouTube] ERROR: {e}")

    # 2b) COMENTARIO con CTA en el video (hay que fijarlo manualmente desde Studio)
    if yt_ok and yt_video_id:
        try:
            post_comment(yt_video_id)
            print("[YouTube] Comentario CTA posteado. Acordate de FIJARLO desde Studio.")
        except Exception as e:
            print(f"[YouTube] No se pudo postear el comentario: {e}")

    # 3) BORRAR LOCAL solo si Drive funciono (es nuestro backup)
    print()
    if drive_ok:
        print("[Limpieza] Drive OK, borrando archivos locales...")
        for p in (video_path, cover_path, meta_path):
            if p.exists():
                p.unlink()
        print("[Limpieza] Listo. El backup queda en Drive.")
    else:
        print("[Limpieza] Drive FALLO, mantengo los archivos locales para reintentar.")
        print(f"  Archivos en: {video_path.parent}")

    # Resumen final
    print()
    print("=== RESUMEN ===")
    print(f"  Drive:   {'OK -> ' + drive_link if drive_ok else 'FALLO'}")
    print(f"  YouTube: {'OK -> ' + yt_url if yt_ok else 'FALLO'}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("url", help="Link del video de YouTube")
    p.add_argument("--keep-temp", action="store_true",
                   help="No borrar la carpeta temp/ al terminar")
    p.add_argument("--style", choices=CENTER_STYLES, default=None,
                   help="Forzar estilo del centro (laptop o vinyl). "
                        "Sin esto, se elige al azar.")
    p.add_argument("--bg", choices=("white", "black"), default="white",
                   help="Color de fondo del video (default: white).")
    p.add_argument("--no-upload", action="store_true",
                   help="Solo generar el video local, no subir a Drive ni YouTube.")
    p.add_argument("--publish-date", default=None,
                   help="Fecha de publicacion en YouTube (YYYY-MM-DD). "
                        "Si no se especifica, programa para la proxima ocurrencia de las 12:00 hs.")
    p.add_argument("--artists", default=None,
                   help="Artistas separados por coma (ej: 'Rubikdice, MC X'). "
                        "Si no se especifica, te pregunto al subir.")
    p.add_argument("--label", default=None,
                   help="Nombre del label (ej: 'Independent').")
    p.add_argument("--skip-prompt", action="store_true",
                   help="No preguntes artistas/label, usa los defaults silenciosamente.")
    args = p.parse_args()
    parsed_artists = None
    if args.artists:
        parsed_artists = [a.strip() for a in args.artists.split(",") if a.strip()]
    run(args.url, keep_temp=args.keep_temp, force_style=args.style, bg=args.bg,
        upload=not args.no_upload, publish_date=args.publish_date,
        artists=parsed_artists, label=args.label, skip_prompt=args.skip_prompt)


if __name__ == "__main__":
    main()
