"""
Sube un video a YouTube con metadata + thumbnail + publishAt programado.

Uso:
    from youtube_upload import upload_video_to_youtube
    info = upload_video_to_youtube(video_path, cover_path, meta_path)

Comportamiento:
- privacyStatus = 'private' + publishAt = proxima ocurrencia de las 12:00 hs locales
- Si publishAt ya paso hoy, se programa para manana 12:00
- El cover.png se sube como thumbnail personalizado del video
"""
from __future__ import annotations
import re
from datetime import datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from google_auth import get_credentials

LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
PUBLISH_HOUR = 12  # publicar a las 12:00 hs locales

YOUTUBE_CATEGORY_MUSIC = "10"


def _yt_service():
    return build("youtube", "v3", credentials=get_credentials(), cache_discovery=False)


def parse_metadata_txt(meta_path: Path) -> dict:
    """Parsea el .txt generado por make_video.py para sacar title/desc/tags."""
    txt = meta_path.read_text(encoding="utf-8")
    sections = {}
    current = None
    buf: list[str] = []
    for line in txt.splitlines():
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


def next_publish_at_iso(hour: int = PUBLISH_HOUR, tz: ZoneInfo = LOCAL_TZ) -> str:
    """Devuelve la proxima ocurrencia de HH:00 en ISO 8601 UTC.
    Si ya paso hoy, lo programa para manana.
    """
    now = datetime.now(tz)
    target = datetime.combine(now.date(), time(hour, 0), tzinfo=tz)
    if now >= target:
        target = target + timedelta(days=1)
    return target.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def specific_date_publish_at_iso(date_str: str, hour: int = PUBLISH_HOUR,
                                 tz: ZoneInfo = LOCAL_TZ) -> str:
    """Devuelve un ISO UTC para una fecha especifica YYYY-MM-DD a HH:00 local."""
    from datetime import date as _date
    y, m, d = (int(x) for x in date_str.split("-"))
    target = datetime.combine(_date(y, m, d), time(hour, 0), tzinfo=tz)
    if target <= datetime.now(tz):
        raise ValueError(f"La fecha {date_str} {hour}:00 ya pasó.")
    return target.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def upload_video_to_youtube(video_path: Path, cover_path: Path,
                            meta_path: Path,
                            publish_hour: int = PUBLISH_HOUR,
                            publish_date: str | None = None) -> dict:
    """Sube el video con metadata + thumbnail. Devuelve info del video subido.

    publish_date: opcional, "YYYY-MM-DD". Si se da, programa para esa fecha
                  a publish_hour:00 local. Sin fecha => proxima ocurrencia
                  de publish_hour:00 (hoy si no paso, sino mañana).
    """
    service = _yt_service()
    meta = parse_metadata_txt(meta_path)
    if publish_date:
        publish_at = specific_date_publish_at_iso(publish_date, publish_hour)
    else:
        publish_at = next_publish_at_iso(publish_hour)

    body = {
        "snippet": {
            "title": meta["title"][:100],  # YouTube limita el titulo a 100 chars
            "description": meta["description"][:5000],
            "tags": meta["tags"][:30],
            "categoryId": YOUTUBE_CATEGORY_MUSIC,
            "defaultLanguage": "es",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
        notifySubscribers=False,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
    video_id = response["id"]

    # Subir thumbnail
    if cover_path.exists():
        try:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(cover_path), mimetype="image/png"),
            ).execute()
            thumb_ok = True
        except Exception as e:
            thumb_ok = False
            thumb_error = str(e)
        else:
            thumb_error = None
    else:
        thumb_ok = False
        thumb_error = "cover.png no encontrado"

    return {
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
        "publish_at": publish_at,
        "thumbnail_uploaded": thumb_ok,
        "thumbnail_error": thumb_error,
    }


DEFAULT_PINNED_COMMENT = (
    "🔥 Subscribe and turn on 🔔 notifications to never miss a viral song!\n"
    "👇 Which song do you want us to upload next? Drop it in the comments.\n"
    "📲 Share this video with your friends!"
)


def post_comment(video_id: str, text: str = DEFAULT_PINNED_COMMENT) -> dict:
    """Postea un comentario top-level en el video.
    NOTA: la API de YouTube NO permite fijar comentarios programaticamente.
    Hay que entrar al video y fijarlo manualmente desde el menu de cada comentario
    (3 puntos -> Pin / Fijar). Solo hace falta hacerlo una vez por video.
    """
    service = _yt_service()
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {
                "snippet": {"textOriginal": text}
            },
        }
    }
    return service.commentThreads().insert(part="snippet", body=body).execute()


if __name__ == "__main__":
    # Test: solo verifica que conectamos OK con YouTube y muestra el canal
    service = _yt_service()
    res = service.channels().list(part="snippet", mine=True).execute()
    if res.get("items"):
        ch = res["items"][0]["snippet"]
        print(f"Canal conectado: {ch['title']}")
        print(f"Proxima publicacion programada para: {next_publish_at_iso()}")
    else:
        print("WARN: no se encontro un canal asociado a esta cuenta")
