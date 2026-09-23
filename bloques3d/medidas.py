"""Medidas compatibles con LEGO (en milimetros) y plan geometrico de cada pieza.

Este modulo es Python puro: lo usan las pruebas (CPython 3.14) y tambien el
Python 3.13 que trae Blender. No importa ``bpy`` ni nada fuera de la stdlib.

Convenciones
------------
* 1 unidad = 1 mm.
* Una pieza ``AxB`` tiene ``A`` studs de ancho (eje Y) y ``B`` de largo (eje X).
* El origen de cada pieza esta en el **centro de su cara inferior**: ``z = 0``
  significa "apoyada en el suelo" y la pieza ocupa ``0 <= z <= altura``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- Medidas de referencia (mm) -------------------------------------------------
PASO = 8.0                 # distancia entre centros de studs
ALTURA_PLACA = 3.2         # una placa; un ladrillo son 3 placas
ALTURA_LADRILLO = 3 * ALTURA_PLACA
STUD_DIAMETRO = 4.8
STUD_ALTURA = 1.7
PARED = 1.2                # grosor de las paredes laterales
TECHO = 1.0                # grosor de la cara superior
TUBO_DIAMETRO_EXT = 6.51   # tubo inferior de las piezas 2xN (toca 4 studs)
TUBO_DIAMETRO_INT = 4.8
BARRA_DIAMETRO = 3.2       # barra inferior de las piezas 1xN
HOLGURA = 0.1              # holgura por lado: un 2x4 mide 31.8 x 15.8 mm

TIPOS = ("ladrillo", "placa", "baldosa")
PLACAS_POR_TIPO = {"ladrillo": 3, "placa": 1, "baldosa": 1}
MAX_STUDS = 32             # tamano maximo admitido por lado

_CLAVE_RE = re.compile(r"^(ladrillo|placa|baldosa)_(\d+)x(\d+)$")


class MedidaInvalida(ValueError):
    """Se lanza cuando una pieza pedida no tiene sentido fisico."""


def _entero_positivo(nombre: str, valor: object, maximo: int) -> int:
    # bool es subclase de int: True no es un tamano valido.
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise MedidaInvalida(f"{nombre} debe ser un entero, no {valor!r}")
    if not 1 <= valor <= maximo:
        raise MedidaInvalida(f"{nombre} debe estar entre 1 y {maximo}, no {valor}")
    return valor


@dataclass(frozen=True)
class Pieza:
    """Una pieza del catalogo: ``ancho`` x ``largo`` studs y ``placas`` de alto."""

    ancho: int
    largo: int
    placas: int
    tipo: str = "ladrillo"

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise MedidaInvalida(
                f"tipo de pieza desconocido {self.tipo!r}; usa uno de {', '.join(TIPOS)}"
            )
        _entero_positivo("ancho", self.ancho, MAX_STUDS)
        _entero_positivo("largo", self.largo, MAX_STUDS)
        _entero_positivo("placas", self.placas, 12)

    # Constructores con nombre ------------------------------------------------
    @classmethod
    def ladrillo(cls, ancho: int, largo: int) -> "Pieza":
        return cls(ancho, largo, PLACAS_POR_TIPO["ladrillo"], "ladrillo")

    @classmethod
    def placa(cls, ancho: int, largo: int) -> "Pieza":
        return cls(ancho, largo, PLACAS_POR_TIPO["placa"], "placa")

    @classmethod
    def baldosa(cls, ancho: int, largo: int) -> "Pieza":
        return cls(ancho, largo, PLACAS_POR_TIPO["baldosa"], "baldosa")

    # Propiedades derivadas ---------------------------------------------------
    @property
    def clave(self) -> str:
        return f"{self.tipo}_{self.ancho}x{self.largo}"

    @property
    def con_studs(self) -> bool:
        return self.tipo != "baldosa"

    @property
    def altura(self) -> float:
        """Altura del cuerpo sin studs (mm)."""
        return round(self.placas * ALTURA_PLACA, 6)

    @property
    def altura_total(self) -> float:
        """Altura incluyendo los studs (mm)."""
        return round(self.altura + (STUD_ALTURA if self.con_studs else 0.0), 6)

    @property
    def exterior(self) -> tuple[float, float, float]:
        """(largo X, ancho Y, alto Z) del cuerpo en mm, ya con la holgura."""
        return (
            round(self.largo * PASO - 2 * HOLGURA, 6),
            round(self.ancho * PASO - 2 * HOLGURA, 6),
            self.altura,
        )


@dataclass(frozen=True)
class PlanPieza:
    """Todo lo que hace falta para construir la malla, como datos planos."""

    pieza: Pieza
    exterior: tuple[float, float, float]
    cavidad: tuple[float, float, float]
    altura_total: float
    studs: tuple[tuple[float, float], ...]
    tubos: tuple[tuple[float, float], ...]
    barras: tuple[tuple[float, float], ...]
    stud_radio: float = STUD_DIAMETRO / 2
    stud_altura: float = STUD_ALTURA
    tubo_radio_ext: float = TUBO_DIAMETRO_EXT / 2
    tubo_radio_int: float = TUBO_DIAMETRO_INT / 2
    barra_radio: float = BARRA_DIAMETRO / 2

    @property
    def caja(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Caja envolvente local ((xmin, ymin, zmin), (xmax, ymax, zmax))."""
        lx, ly, _ = self.exterior
        return ((-lx / 2, -ly / 2, 0.0), (lx / 2, ly / 2, self.altura_total))


def _centros(n: int) -> list[float]:
    """Centros de n celdas de paso PASO, centrados en 0."""
    return [round((i - (n - 1) / 2) * PASO, 6) for i in range(n)]


def _fronteras(n: int) -> list[float]:
    """Las n-1 lineas interiores entre celdas (donde van tubos y barras)."""
    return [round((i + 1 - n / 2) * PASO, 6) for i in range(n - 1)]


def plan_pieza(pieza: Pieza) -> PlanPieza:
    """Calcula medidas exteriores, cavidad y centros de studs, tubos y barras."""
    if not isinstance(pieza, Pieza):
        raise MedidaInvalida(f"se esperaba una Pieza, no {type(pieza).__name__}")
    lx, ly, h = pieza.exterior
    cavidad = (round(lx - 2 * PARED, 6), round(ly - 2 * PARED, 6), round(h - TECHO, 6))

    studs: tuple[tuple[float, float], ...] = ()
    if pieza.con_studs:
        studs = tuple((x, y) for x in _centros(pieza.largo) for y in _centros(pieza.ancho))

    tubos: tuple[tuple[float, float], ...] = ()
    barras: tuple[tuple[float, float], ...] = ()
    if pieza.ancho >= 2 and pieza.largo >= 2:
        tubos = tuple((x, y) for x in _fronteras(pieza.largo) for y in _fronteras(pieza.ancho))
    elif pieza.ancho == 1 and pieza.largo >= 2:
        barras = tuple((x, 0.0) for x in _fronteras(pieza.largo))
    elif pieza.largo == 1 and pieza.ancho >= 2:
        barras = tuple((0.0, y) for y in _fronteras(pieza.ancho))

    return PlanPieza(
        pieza=pieza,
        exterior=(lx, ly, h),
        cavidad=cavidad,
        altura_total=pieza.altura_total,
        studs=studs,
        tubos=tubos,
        barras=barras,
    )


def pieza_por_clave(clave: str) -> Pieza:
    """Convierte ``"ladrillo_2x4"``, ``"placa_6x8"``... en una :class:`Pieza`.

    Acepta cualquier tamano, no solo los del catalogo.
    """
    if not isinstance(clave, str):
        raise MedidaInvalida(f"la clave de pieza debe ser texto, no {clave!r}")
    m = _CLAVE_RE.match(clave.strip().lower())
    if not m:
        raise MedidaInvalida(
            f"pieza desconocida {clave!r}; el formato es tipo_AxB, p. ej. ladrillo_2x4, "
            f"placa_4x4 o baldosa_2x2"
        )
    tipo, ancho, largo = m.group(1), int(m.group(2)), int(m.group(3))
    return Pieza(ancho, largo, PLACAS_POR_TIPO[tipo], tipo)


# Catalogo "de serie": lo que se construye y se prueba siempre.
CATALOGO: dict[str, Pieza] = {
    p.clave: p
    for p in (
        Pieza.ladrillo(1, 1),
        Pieza.ladrillo(1, 2),
        Pieza.ladrillo(1, 4),
        Pieza.ladrillo(2, 2),
        Pieza.ladrillo(2, 3),
        Pieza.ladrillo(2, 4),
        Pieza.ladrillo(2, 6),
        Pieza.placa(1, 4),
        Pieza.placa(2, 4),
        Pieza.placa(4, 4),
        Pieza.baldosa(1, 2),
        Pieza.baldosa(2, 2),
    )
}
