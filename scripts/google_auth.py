"""
Autenticacion OAuth 2.0 contra Google APIs (YouTube + Drive).

Uso:
    from google_auth import get_credentials
    creds = get_credentials()  # devuelve credenciales validas

Primera vez: abre el browser para login interactivo y guarda token.json.
Llamadas posteriores: lee token.json, refresca si esta vencido.
"""
from __future__ import annotations
from pathlib import Path
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
CRED_DIR = ROOT / "credentials"
CLIENT_SECRET = CRED_DIR / "client_secret.json"
TOKEN_FILE = CRED_DIR / "token.json"

# Permisos pedidos. Cuanto menor sea el scope, mejor (principio de minimo privilegio).
SCOPES = [
    # YouTube: subir videos y leer metadatos del propio canal
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    # Drive: solo archivos creados por esta app (no toca el resto del Drive)
    "https://www.googleapis.com/auth/drive.file",
]


def get_credentials() -> Credentials:
    """Devuelve credenciales OAuth validas. Refresca token o pide login si hace falta."""
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f"Falta {CLIENT_SECRET}. Descarga el OAuth client desde Google Cloud."
        )

    creds: Credentials | None = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            # Si el refresh falla, hacemos login interactivo desde cero
            pass

    # Login interactivo: abre el browser
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        authorization_prompt_message=(
            "Abriendo el navegador para autorizar Aura Infinite 10 Uploads...\n"
            "Loguease con viraltrends1rodricci@gmail.com"
        ),
        success_message=(
            "Autorizacion exitosa. Ya podes cerrar esta ventana del navegador."
        ),
    )
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    return creds


if __name__ == "__main__":
    creds = get_credentials()
    print(f"OK - credenciales validas. Token guardado en: {TOKEN_FILE}")
    print(f"Scopes autorizados: {len(creds.scopes or [])}")
