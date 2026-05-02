"""
Quita fondos solidos (blancos o cercanos al blanco) de una imagen.
Convierte los pixeles claros del borde en transparencia.

Uso:
    python remove_bg.py <input.jpg> <output.png> [--threshold 230] [--edge-only]

threshold: brillo minimo (0-255) para considerar un pixel como "fondo".
edge-only: solo borra pixeles claros conectados al borde (recomendado para
           no borrar partes claras del personaje en el medio).
"""
from __future__ import annotations
import sys
from collections import deque
from pathlib import Path
from PIL import Image


def remove_white_bg(in_path: Path, out_path: Path,
                    threshold: int = 230, edge_only: bool = True) -> None:
    img = Image.open(in_path).convert("RGBA")
    w, h = img.size
    px = img.load()

    if not edge_only:
        # Modo simple: cualquier pixel claro -> transparente
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                if r >= threshold and g >= threshold and b >= threshold:
                    px[x, y] = (r, g, b, 0)
    else:
        # Flood fill desde los bordes hacia adentro: solo el fondo conectado al borde se vuelve transparente.
        # Mas seguro: no borra partes claras internas del personaje.
        visited = bytearray(w * h)
        q: deque[tuple[int, int]] = deque()

        def is_bg(x: int, y: int) -> bool:
            r, g, b, _a = px[x, y]
            return r >= threshold and g >= threshold and b >= threshold

        # Sembrar desde los 4 bordes
        for x in range(w):
            for y in (0, h - 1):
                if not visited[y * w + x] and is_bg(x, y):
                    q.append((x, y))
                    visited[y * w + x] = 1
        for y in range(h):
            for x in (0, w - 1):
                if not visited[y * w + x] and is_bg(x, y):
                    q.append((x, y))
                    visited[y * w + x] = 1

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

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    print(f"OK -> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    in_p = Path(sys.argv[1])
    out_p = Path(sys.argv[2])
    threshold = 230
    edge_only = True
    args = sys.argv[3:]
    if "--threshold" in args:
        threshold = int(args[args.index("--threshold") + 1])
    if "--no-edge-only" in args:
        edge_only = False
    remove_white_bg(in_p, out_p, threshold=threshold, edge_only=edge_only)
