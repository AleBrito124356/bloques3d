"""Opciones de render compartidas por la CLI y por el script de Blender."""
from __future__ import annotations

import argparse
import re

MOTORES = ("eevee", "cycles")


def resolucion(texto: str) -> tuple[int, int]:
    """``"1920x1080"`` -> ``(1920, 1080)``."""
    m = re.fullmatch(r"\s*(\d{2,5})\s*[xX]\s*(\d{2,5})\s*", texto or "")
    if not m:
        raise argparse.ArgumentTypeError(f"resolución no válida {texto!r}; usa ANCHOxALTO, p. ej. 1920x1080")
    ancho, alto = int(m.group(1)), int(m.group(2))
    if not (16 <= ancho <= 8192 and 16 <= alto <= 8192):
        raise argparse.ArgumentTypeError("cada lado de la resolución debe estar entre 16 y 8192 píxeles")
    return ancho, alto


def _entero_en(minimo: int, maximo: int, nombre: str):
    def conv(texto: str) -> int:
        try:
            v = int(texto)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{nombre} debe ser un entero, no {texto!r}") from None
        if not minimo <= v <= maximo:
            raise argparse.ArgumentTypeError(f"{nombre} debe estar entre {minimo} y {maximo}")
        return v
    return conv


def anadir_opciones_render(p: argparse.ArgumentParser) -> None:
    p.add_argument("--salida", default="salida",
                   help="carpeta donde se escriben <escena>.blend, .png y .jpg (por defecto: salida)")
    p.add_argument("--res", type=resolucion, default=(1920, 1080), metavar="ANCHOxALTO",
                   help="resolución del render (por defecto 1920x1080)")
    p.add_argument("--muestras", type=_entero_en(1, 4096, "--muestras"), default=64,
                   help="muestras por píxel (por defecto 64)")
    p.add_argument("--motor", choices=MOTORES, default="eevee", help="motor de render (por defecto eevee)")
    p.add_argument("--jpeg", action="store_true", help="guardar también una copia JPEG (calidad 90)")
    p.add_argument("--sin-render", action="store_true",
                   help="solo construir y guardar el .blend")
