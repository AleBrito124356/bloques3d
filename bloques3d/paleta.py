"""Paleta de colores de plastico ABS con nombre en espanol.

Los valores hex son los colores sRGB habituales de las piezas tipo LEGO
(los publicados por las bases de datos de fans). ``lineal()`` los convierte
al espacio lineal que espera el ``Base Color`` del Principled BSDF.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColorABS:
    nombre: str
    hex: str
    rugosidad: float = 0.22
    transparente: bool = False

    @property
    def srgb(self) -> tuple[float, float, float]:
        h = self.hex.lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]

    @property
    def lineal(self) -> tuple[float, float, float]:
        return tuple(srgb_a_lineal(c) for c in self.srgb)  # type: ignore[return-value]


def srgb_a_lineal(c: float) -> float:
    """Funcion de transferencia sRGB inversa (IEC 61966-2-1)."""
    if not 0.0 <= c <= 1.0:
        raise ValueError(f"componente sRGB fuera de [0, 1]: {c}")
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


PALETA: dict[str, ColorABS] = {
    c.nombre: c
    for c in (
        ColorABS("blanco", "#F2F3F2", 0.24),
        ColorABS("negro", "#1B2A34", 0.20),
        ColorABS("gris_claro", "#A0A5A9", 0.24),
        ColorABS("gris_oscuro", "#6C6E68", 0.24),
        ColorABS("rojo", "#C91A09", 0.20),
        ColorABS("azul", "#0055BF", 0.20),
        ColorABS("amarillo", "#F2CD37", 0.22),
        ColorABS("verde", "#237841", 0.20),
        ColorABS("verde_lima", "#BBE90B", 0.22),
        ColorABS("naranja", "#FE8A18", 0.22),
        ColorABS("azul_claro", "#36AEBF", 0.22),
        ColorABS("beige", "#E4CD9E", 0.26),
        ColorABS("marron", "#582A12", 0.22),
        ColorABS("rosa", "#FC97AC", 0.22),
        ColorABS("transparente", "#FCFCFC", 0.04, transparente=True),
    )
}


def color(nombre: str) -> ColorABS:
    try:
        return PALETA[nombre]
    except KeyError:
        raise KeyError(
            f"color desconocido {nombre!r}; disponibles: {', '.join(sorted(PALETA))}"
        ) from None
