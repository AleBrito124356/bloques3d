"""Lector de STL (binario y ASCII) en Python puro, para comprobar exportaciones."""
from __future__ import annotations

import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

Punto = tuple[float, float, float]


@dataclass
class MallaSTL:
    triangulos: list[tuple[Punto, Punto, Punto]]

    def __len__(self) -> int:
        return len(self.triangulos)

    def caja(self) -> tuple[Punto, Punto]:
        pts = [p for t in self.triangulos for p in t]
        return (
            (min(p[0] for p in pts), min(p[1] for p in pts), min(p[2] for p in pts)),
            (max(p[0] for p in pts), max(p[1] for p in pts), max(p[2] for p in pts)),
        )

    def dimensiones(self) -> Punto:
        lo, hi = self.caja()
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    def uso_de_aristas(self, decimales: int = 4) -> Counter:
        """Cuantos triangulos comparten cada arista (vertices soldados por posicion)."""
        def clave(p: Punto) -> Punto:
            return tuple(round(c, decimales) + 0.0 for c in p)  # +0.0 quita el -0.0

        usos: Counter = Counter()
        for t in self.triangulos:
            a, b, c = (clave(p) for p in t)
            for u, v in ((a, b), (b, c), (c, a)):
                usos[(u, v) if u <= v else (v, u)] += 1
        return usos

    def aristas_no_cerradas(self) -> int:
        """Aristas que no comparten exactamente 2 triangulos (0 = estanca)."""
        return sum(1 for n in self.uso_de_aristas().values() if n != 2)

    def triangulos_degenerados(self, area_min: float = 1e-9) -> int:
        n = 0
        for a, b, c in self.triangulos:
            u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            cx = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            if (cx[0] ** 2 + cx[1] ** 2 + cx[2] ** 2) ** 0.5 / 2 < area_min:
                n += 1
        return n


def leer_stl(ruta: str | Path) -> MallaSTL:
    datos = Path(ruta).read_bytes()
    if len(datos) >= 84:
        n = struct.unpack_from("<I", datos, 80)[0]
        if len(datos) == 84 + 50 * n:
            tris = []
            for i in range(n):
                v = struct.unpack_from("<12f", datos, 84 + 50 * i)
                tris.append((tuple(v[3:6]), tuple(v[6:9]), tuple(v[9:12])))
            return MallaSTL(tris)  # type: ignore[arg-type]
    texto = datos.decode("ascii", errors="strict")
    if not texto.lstrip().startswith("solid"):
        raise ValueError(f"{ruta} no es un STL binario ni ASCII valido")
    verts = [tuple(float(x) for x in linea.split()[1:4])
             for linea in texto.splitlines() if linea.strip().startswith("vertex")]
    if len(verts) % 3:
        raise ValueError(f"{ruta}: numero de vertices no multiplo de 3")
    return MallaSTL([tuple(verts[i:i + 3]) for i in range(0, len(verts), 3)])  # type: ignore[misc]


def escribir_stl_binario(ruta: str | Path, triangulos) -> None:
    """Solo para las pruebas del propio lector."""
    partes = [b"bloques3d-test".ljust(80, b"\0"), struct.pack("<I", len(triangulos))]
    for t in triangulos:
        partes.append(struct.pack("<12fH", 0, 0, 0, *t[0], *t[1], *t[2], 0))
    Path(ruta).write_bytes(b"".join(partes))
