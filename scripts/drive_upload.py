"""
Sube archivos del canal a Google Drive en una carpeta dedicada.

Uso:
    from drive_upload import upload_video_to_drive
    folder_id = upload_video_to_drive(video_path, cover_path, meta_path, slug="travieso")

Estructura en Drive:
    Aura Infinite 10 - Videos/
        2026-05-02_travieso/
            travieso.mp4
            travieso_cover.png
            travieso.txt
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from google_auth import get_credentials

DRIVE_PARENT_FOLDER_NAME = "Aura Infinite 10 - Videos"


def _drive_service():
    return build("drive", "v3", credentials=get_credentials(), cache_discovery=False)


def _find_or_create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Devuelve el id de la carpeta. La crea si no existe."""
    query = (
        f"mimeType = 'application/vnd.google-apps.folder' and "
        f"name = '{name}' and trashed = false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"
    result = service.files().list(
        q=query, spaces="drive", fields="files(id, name)"
    ).execute()
    files = result.get("files", [])
    if files:
        return files[0]["id"]
    # Crear
    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def _upload_file(service, file_path: Path, parent_id: str, mime: str) -> dict:
    media = MediaFileUpload(str(file_path), mimetype=mime, resumable=True)
    body = {"name": file_path.name, "parents": [parent_id]}
    result = service.files().create(
        body=body, media_body=media, fields="id, name, webViewLink"
    ).execute()
    return result


def upload_video_to_drive(video_path: Path, cover_path: Path,
                          meta_path: Path, slug: str) -> dict:
    """Sube los 3 archivos de un video a una subcarpeta dedicada en Drive.

    Devuelve dict con info: {folder_id, folder_link, video_id, ...}
    """
    service = _drive_service()
    # Carpeta padre del canal (compartida por todos los videos)
    parent_id = _find_or_create_folder(service, DRIVE_PARENT_FOLDER_NAME)
    # Subcarpeta del video del dia: YYYY-MM-DD_slug
    today = datetime.now().strftime("%Y-%m-%d")
    sub_name = f"{today}_{slug}"
    sub_id = _find_or_create_folder(service, sub_name, parent_id=parent_id)

    results = {}
    if video_path.exists():
        r = _upload_file(service, video_path, sub_id, "video/mp4")
        results["video"] = r
    if cover_path.exists():
        r = _upload_file(service, cover_path, sub_id, "image/png")
        results["cover"] = r
    if meta_path.exists():
        r = _upload_file(service, meta_path, sub_id, "text/plain")
        results["meta"] = r

    folder = service.files().get(
        fileId=sub_id, fields="id, name, webViewLink"
    ).execute()
    return {
        "folder_id": sub_id,
        "folder_name": folder["name"],
        "folder_link": folder.get("webViewLink"),
        "files": results,
    }


if __name__ == "__main__":
    # Test rapido: crea la carpeta padre del canal si no existe
    service = _drive_service()
    parent_id = _find_or_create_folder(service, DRIVE_PARENT_FOLDER_NAME)
    folder = service.files().get(fileId=parent_id, fields="webViewLink").execute()
    print(f"Carpeta del canal: {DRIVE_PARENT_FOLDER_NAME}")
    print(f"Link: {folder.get('webViewLink')}")
