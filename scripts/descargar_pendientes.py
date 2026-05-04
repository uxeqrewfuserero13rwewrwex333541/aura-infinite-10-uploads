"""
Descarga local los audios + thumbnails de canciones pendientes en la cola.

Workflow tipico:
    1. Pasas links nuevos (los agregas a queue.csv como pendientes)
    2. Corres este script: descarga, extrae metadata, marca con audio_local
    3. git add audios/ queue.csv && git commit && git push
    4. Github Actions usa esos archivos del repo (sin tocar YouTube para descargar)

Uso:
    python descargar_pendientes.py [--max N]

--max: cuantos audios descargar como maximo en esta corrida (default: todos)
"""
from __future__ import annotations
import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from imageio_ffmpeg import get_ffmpeg_exe
from musicbrainz_lookup import parse_youtube_auto_description

QUEUE_PATH = ROOT / "queue.csv"
AUDIOS_DIR = ROOT / "audios"
VENV_BIN = ROOT / "venv" / "bin"
YT_DLP = str(VENV_BIN / "yt-dlp") if (VENV_BIN / "yt-dlp").exists() else "yt-dlp"
FFMPEG = get_ffmpeg_exe()

COLUMNS = ["url", "publish_date", "estado", "uploaded_at", "video_id",
           "drive_link", "audio_local", "title", "artists", "label", "notas"]


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:max_len].strip("_") or "video"


def url_to_id(url: str) -> str:
    """Extrae el video_id de una url tipo https://youtu.be/XYZ?si=..."""
    m = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", url)
    return m.group(1) if m else slugify(url)


def load_queue() -> list[dict]:
    with QUEUE_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_queue(rows: list[dict]) -> None:
    with QUEUE_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def fetch_metadata(url: str) -> dict:
    """Solo metadata (sin descargar)."""
    res = subprocess.run(
        [YT_DLP, "--dump-single-json", "--no-warnings", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(res.stdout)


def download_audio_and_thumb(url: str, dest_dir: Path) -> None:
    """Descarga audio mp3 + thumbnail jpg en dest_dir/song.mp3 y dest_dir/song.jpg."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        YT_DLP,
        "--ffmpeg-location", FFMPEG,
        "-x", "--audio-format", "mp3", "--audio-quality", "0",
        "--write-thumbnail", "--convert-thumbnails", "jpg",
        "-o", str(dest_dir / "song.%(ext)s"),
        "--no-warnings",
        url,
    ], check=True, capture_output=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--max", type=int, default=None,
                   help="Maximo de audios a descargar en esta corrida")
    args = p.parse_args()

    rows = load_queue()
    pending_to_download = [
        (i, r) for i, r in enumerate(rows)
        if (r.get("estado") or "").strip() == "pendiente"
        and not (r.get("audio_local") or "").strip()
    ]
    if not pending_to_download:
        print("No hay pendientes sin audio_local. Nada que hacer.")
        sys.exit(0)

    if args.max:
        pending_to_download = pending_to_download[:args.max]

    print(f"Voy a descargar {len(pending_to_download)} audio(s).")
    AUDIOS_DIR.mkdir(parents=True, exist_ok=True)

    ok_count = 0
    fail_count = 0
    for i, row in pending_to_download:
        url = row["url"].strip()
        vid = url_to_id(url)
        print(f"\n--- {url} ---")
        try:
            print("  [1/3] Metadata...")
            meta = fetch_metadata(url)
            title = meta.get("title", "video")
            uploader = meta.get("uploader", "")
            duration = int(meta.get("duration") or 0)
            yt_desc = meta.get("description", "") or ""

            slug = slugify(title)
            print(f"  Titulo: {title}")
            print(f"  Duracion: {duration}s")

            print("  [2/3] Parseando artistas + label...")
            parsed = parse_youtube_auto_description(yt_desc)
            if parsed["matched"]:
                artists = parsed["artists"]
                label = parsed["label"] or "Independent"
                print(f"  Artists: {artists}")
                print(f"  Label: {label}")
            else:
                artists = [uploader] if uploader else ["Various Artists"]
                label = "Independent"
                print(f"  Sin auto-desc, default: {artists} / {label}")

            print("  [3/3] Descargando audio + thumbnail...")
            dest = AUDIOS_DIR / vid
            download_audio_and_thumb(url, dest)
            audio_path = dest / "song.mp3"
            thumb_path = dest / "song.jpg"
            if not audio_path.exists() or not thumb_path.exists():
                raise RuntimeError("Faltan archivos descargados")
            size_mb = audio_path.stat().st_size / 1024 / 1024
            print(f"  OK -> {dest.relative_to(ROOT)} ({size_mb:.1f} MB)")

            # Actualizar fila del queue
            row["audio_local"] = str(dest.relative_to(ROOT))
            row["title"] = title
            row["artists"] = "|".join(artists)  # separador para evitar conflictos con coma del CSV
            row["label"] = label
            ok_count += 1

        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="ignore")[-500:]
            print(f"  ERROR yt-dlp: {err}")
            row["notas"] = (row.get("notas", "") + f" | descarga local fallo: {err[:200]}").strip(" |")[:500]
            fail_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            row["notas"] = (row.get("notas", "") + f" | descarga local fallo: {e}").strip(" |")[:500]
            fail_count += 1

    save_queue(rows)
    print(f"\n=== RESUMEN ===")
    print(f"  OK:    {ok_count}")
    print(f"  Fallo: {fail_count}")
    print(f"\nProximo paso:")
    print(f"  git add audios/ queue.csv && git commit -m 'chore: descargar audios' && git push")


if __name__ == "__main__":
    main()
