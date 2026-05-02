"""
Actualiza la metadata (titulo / descripcion / tags) de videos ya subidos al canal.

Uso:
    python update_existing_videos.py

Cada video se asocia con su URL fuente original para poder re-extraer artistas/label
desde la descripcion auto-generada de YouTube.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from google_auth import get_credentials
from googleapiclient.discovery import build

from make_video import build_youtube_metadata
from musicbrainz_lookup import parse_youtube_auto_description

# Mapeo: video_id de NUESTRO canal -> URL del video fuente para sacar metadata
VIDEOS_TO_UPDATE = [
    {
        "our_video_id": "4ZmfeLUyFco",
        "source_url": "https://youtu.be/UogMUVQqBeE",  # TRAVIESO
    },
    {
        "our_video_id": "eMjJypv1ndE",
        "source_url": "https://youtu.be/4E4VaL5krv8",  # PEGADORA
    },
    {
        "our_video_id": "aqF2niokn3A",
        "source_url": "https://youtu.be/IIgsVfn3l6g",  # VOCE NA MIRA
    },
    {
        "our_video_id": "kOwH3d5EHww",
        "source_url": "https://youtu.be/6snDsbwxRUI",  # ALQUIMIA
    },
]


def fetch_source_meta(url: str) -> dict:
    """Descarga metadata del video fuente con yt-dlp (sin bajar audio/video)."""
    out = subprocess.run(
        [str(ROOT / "venv" / "bin" / "yt-dlp"),
         "--dump-single-json", "--no-warnings", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def parse_metadata_txt(text: str) -> dict:
    """Parsea el output de build_youtube_metadata() en {title, description, tags}."""
    sections = {}
    current = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^=== (\w+) ===\s*$", line)
        if m:
            if current:
                sections[current] = "\n".join(buf).strip()
            current = m.group(1).upper()
            buf = []
        elif current:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()
    title = sections.get("TITULO", "Untitled").strip()
    description = sections.get("DESCRIPCION", "").strip()
    tags_raw = sections.get("TAGS", "").strip()
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
    return {"title": title, "description": description, "tags": tags}


def update_video_metadata(service, our_video_id: str, source_url: str) -> dict:
    print(f"\n=== Actualizando {our_video_id} (fuente: {source_url}) ===")
    src_meta = fetch_source_meta(source_url)
    title = src_meta.get("title", "Untitled")
    uploader = src_meta.get("uploader", "")
    desc = src_meta.get("description", "") or ""

    parsed = parse_youtube_auto_description(desc)
    if parsed["matched"]:
        artists = parsed["artists"]
        label = parsed["label"] or "Independent"
        print(f"  Artistas extraidos: {artists}")
        print(f"  Label: {label}")
    else:
        artists = [uploader] if uploader else ["Various Artists"]
        label = "Independent"
        print(f"  No se pudo parsear, usando defaults: {artists} / {label}")

    new_meta_text = build_youtube_metadata(src_meta, artists=artists, label=label)
    parsed_new = parse_metadata_txt(new_meta_text)

    # Obtener categoryId actual (no queremos cambiarlo)
    current = service.videos().list(part="snippet", id=our_video_id).execute()
    if not current["items"]:
        print(f"  ERROR: video {our_video_id} no encontrado")
        return {"ok": False}
    snip = current["items"][0]["snippet"]

    body = {
        "id": our_video_id,
        "snippet": {
            "title": parsed_new["title"][:100],
            "description": parsed_new["description"][:5000],
            "tags": parsed_new["tags"][:30],
            "categoryId": snip.get("categoryId", "10"),
            "defaultLanguage": "en",
        },
    }
    service.videos().update(part="snippet", body=body).execute()
    print(f"  OK actualizado")
    return {"ok": True, "artists": artists, "label": label}


def main():
    service = build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)
    for video in VIDEOS_TO_UPDATE:
        try:
            update_video_metadata(service, video["our_video_id"], video["source_url"])
        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
