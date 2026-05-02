"""
Toma los proximos N videos PENDIENTES de queue.csv y los sube programados.

Logica de fechas (default):
  - 1er pendiente -> publica en hoy + 4 dias 12:00 hs locales
  - 2do pendiente -> publica en hoy + 5 dias 12:00 hs locales

Asi cada vez que corre quedan +2 videos en cola y siempre hay buffer.

Uso:
    python subir_lote.py [--count N] [--first-offset DIAS] [--gap DIAS]

CSV: url, publish_date, estado, uploaded_at, video_id, drive_link, notas
  estado: 'pendiente' | 'subido' | 'error' | 'omitir'
"""
from __future__ import annotations
import argparse
import csv
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from make_video import run as make_video_run

QUEUE_PATH = ROOT / "queue.csv"
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
COLUMNS = ["url", "publish_date", "estado", "uploaded_at",
           "video_id", "drive_link", "notas"]


def load_queue() -> list[dict]:
    if not QUEUE_PATH.exists():
        return []
    with QUEUE_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_queue(rows: list[dict]) -> None:
    with QUEUE_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def pick_pending(rows: list[dict], n: int) -> list[int]:
    """Devuelve los indices de las primeras N filas con estado='pendiente'."""
    out: list[int] = []
    for i, r in enumerate(rows):
        if (r.get("estado") or "pendiente").strip().lower() == "pendiente":
            out.append(i)
            if len(out) >= n:
                break
    return out


def date_in_days(days: int) -> str:
    """YYYY-MM-DD para hoy + N dias en hora local."""
    return (datetime.now(LOCAL_TZ) + timedelta(days=days)).date().isoformat()


def parse_date(s: str) -> str:
    """Acepta YYYY-MM-DD o '+Nd'. Devuelve YYYY-MM-DD absoluta."""
    s = s.strip()
    if s.startswith("+") and s.endswith("d"):
        return date_in_days(int(s[1:-1]))
    # Validar formato
    datetime.strptime(s, "%Y-%m-%d")
    return s


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=2,
                   help="Cuantos videos subir en este lote (default 2)")
    p.add_argument("--first-offset", type=int, default=4,
                   help="Cuantos dias en el futuro publicar el 1er video (default 4)")
    p.add_argument("--gap", type=int, default=1,
                   help="Cuantos dias entre videos consecutivos (default 1)")
    p.add_argument("--dry-run", action="store_true",
                   help="No sube nada, solo muestra que se haria")
    args = p.parse_args()

    rows = load_queue()
    if not rows:
        print(f"queue.csv vacio o no existe ({QUEUE_PATH})")
        sys.exit(0)

    indexes = pick_pending(rows, args.count)
    if not indexes:
        print("No hay videos pendientes en la cola")
        sys.exit(0)

    print(f"Procesando {len(indexes)} video(s) pendientes:")
    for offset_idx, row_idx in enumerate(indexes):
        row = rows[row_idx]
        url = row["url"].strip()
        # publish_date: si la fila ya tiene una explicita, respetarla
        explicit = (row.get("publish_date") or "").strip()
        if explicit:
            try:
                publish_date = parse_date(explicit)
            except Exception:
                publish_date = date_in_days(args.first_offset + offset_idx * args.gap)
        else:
            publish_date = date_in_days(args.first_offset + offset_idx * args.gap)

        print(f"\n--- {url}  ->  publica {publish_date} 12hs ---")
        if args.dry_run:
            print("(dry-run, no subo nada)")
            continue
        try:
            make_video_run(
                url=url,
                upload=True,
                publish_date=publish_date,
                skip_prompt=True,  # en automatico no podemos preguntar
            )
            row["estado"] = "subido"
            row["uploaded_at"] = datetime.now(LOCAL_TZ).isoformat(timespec="seconds")
            row["publish_date"] = publish_date
            save_queue(rows)
            print(f"OK -> marcado como 'subido' en queue.csv")
        except Exception as e:
            row["estado"] = "error"
            row["notas"] = (row.get("notas", "") + f" | error: {e}")[:500]
            save_queue(rows)
            print(f"ERROR: {e}")

    print("\nResumen final de la cola:")
    pendientes = sum(1 for r in rows if (r.get("estado") or "pendiente").strip().lower() == "pendiente")
    print(f"  pendientes restantes: {pendientes}")


if __name__ == "__main__":
    main()
