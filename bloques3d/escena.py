"""Escenas declarativas (JSON) sobre la rejilla de studs.

Python puro (sin ``bpy``): se valida igual en la linea de comandos que
dentro de Blender.

Formato
-------
.. code-block:: json

    {
      "nombre": "trio",
      "camara": {"azimut": 32, "elevacion": 30, "lente": 70},
      "piezas": [
        {"id": "azul",   "pieza": "ladrillo_2x4", "color": "azul",   "pos": [0, 0]},
        {"id": "blanco", "pieza": "ladrillo_2x4", "color": "blanco", "pos": [2, 1], "nivel": 3},
        {"id": "rojo",   "pieza": "ladrillo_2x4", "color": "rojo",   "pos": [5.2, -3.4], "angulo": 9}
      ]
    }

* ``pos`` es la celda de la esquina minima (x, y) de la huella, en studs.
* ``nivel`` es la altura de la cara inferior, en placas (un ladrillo = 3).
* ``rot`` gira la pieza 0/90/180/270 grados sobre su centro.
* ``angulo`` (grados, libre) solo vale para piezas **sueltas en el suelo**:
  no se enganchan a la rejilla y nada puede apoyarse en ellas.
"""
from __future__ import annotations

import json
import math
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from .medidas import ALTURA_PLACA, PASO, MedidaInvalida, Pieza, pieza_por_clave
from .paleta import PALETA

ROTACIONES = (0, 90, 180, 270)
MAX_PIEZAS = 5000
_CLAVES_PIEZA = {"id", "pieza", "color", "pos", "nivel", "rot", "angulo"}
_CLAVES_ESCENA = {"nombre", "descripcion", "camara", "fondo", "piezas"}
_CLAVES_CAMARA = {"azimut", "elevacion", "lente", "margen", "enfoque", "apertura"}
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class EscenaInvalida(ValueError):
    """La escena tiene uno o mas problemas; ``errores`` los lista todos."""

    def __init__(self, errores: list[str], origen: str = "la escena"):
        self.errores = list(errores)
        self.origen = origen
        cuerpo = "\n".join(f"  - {e}" for e in self.errores)
        super().__init__(f"{origen} no es válida ({len(self.errores)} problema(s)):\n{cuerpo}")


@dataclass(frozen=True)
class Colocacion:
    """Una pieza colocada en la escena."""

    id: str
    pieza: Pieza
    color: str
    x: float
    y: float
    nivel: int = 0
    rot: int = 0
    angulo: float | None = None

    @property
    def suelta(self) -> bool:
        return self.angulo is not None

    @property
    def huella(self) -> tuple[int, int]:
        """Studs que ocupa en (X, Y) tras la rotacion de rejilla."""
        if self.rot in (90, 270):
            return (self.pieza.ancho, self.pieza.largo)
        return (self.pieza.largo, self.pieza.ancho)

    @property
    def giro_grados(self) -> float:
        return float(self.rot) + (self.angulo or 0.0)

    @property
    def centro_mm(self) -> tuple[float, float, float]:
        """Centro de la cara inferior en coordenadas del mundo (mm)."""
        nx, ny = self.huella
        return (
            round((self.x + nx / 2) * PASO, 6),
            round((self.y + ny / 2) * PASO, 6),
            round(self.nivel * ALTURA_PLACA, 6),
        )

    @property
    def z_min(self) -> float:
        return self.centro_mm[2]

    @property
    def z_max(self) -> float:
        """Altura del punto mas alto (con studs)."""
        return round(self.z_min + self.pieza.altura_total, 6)

    @property
    def nivel_superior(self) -> int:
        """Nivel (en placas) de la cara superior del cuerpo."""
        return self.nivel + self.pieza.placas

    def celdas(self) -> set[tuple[int, int, int]]:
        """Celdas (x, y, nivel) que ocupa el cuerpo. Solo piezas de rejilla."""
        if self.suelta:
            raise ValueError("una pieza suelta no ocupa celdas de la rejilla")
        nx, ny = self.huella
        x0, y0 = int(self.x), int(self.y)
        return {
            (x, y, z)
            for x in range(x0, x0 + nx)
            for y in range(y0, y0 + ny)
            for z in range(self.nivel, self.nivel + self.pieza.placas)
        }

    def huella_celdas(self) -> set[tuple[int, int]]:
        nx, ny = self.huella
        x0, y0 = int(self.x), int(self.y)
        return {(x, y) for x in range(x0, x0 + nx) for y in range(y0, y0 + ny)}

    def rectangulo_mm(self) -> list[tuple[float, float]]:
        """Las 4 esquinas (x, y) del cuerpo en planta, en el mundo (mm)."""
        lx, ly, _ = self.pieza.exterior
        cx, cy, _ = self.centro_mm
        g = math.radians(self.giro_grados)
        c, s = math.cos(g), math.sin(g)
        return [
            (cx + dx * c - dy * s, cy + dx * s + dy * c)
            for dx, dy in ((-lx / 2, -ly / 2), (lx / 2, -ly / 2), (lx / 2, ly / 2), (-lx / 2, ly / 2))
        ]

    def esquinas_mm(self) -> list[tuple[float, float, float]]:
        """Las 8 esquinas de la caja orientada (incluye los studs)."""
        return [(x, y, z) for z in (self.z_min, self.z_max) for x, y in self.rectangulo_mm()]


@dataclass(frozen=True)
class ConfigCamara:
    azimut: float = 32.0        # grados; 0 = camara delante (en -Y) mirando hacia +Y
    elevacion: float = 30.0     # grados sobre el horizonte
    lente: float = 70.0         # mm (sensor de 36 mm)
    margen: float = 0.07        # fraccion del encuadre que queda libre en cada borde
    enfoque: str | None = None  # id de la pieza a enfocar (None = centro de la escena)
    apertura: float | None = None  # f-stop; None desactiva la profundidad de campo


@dataclass(frozen=True)
class Conexion:
    abajo: str
    arriba: str
    studs: int


@dataclass(frozen=True)
class Escena:
    nombre: str
    piezas: tuple[Colocacion, ...]
    camara: ConfigCamara = field(default_factory=ConfigCamara)
    descripcion: str = ""
    fondo: str = "#EDEDEF"

    def por_id(self, id_: str) -> Colocacion:
        for c in self.piezas:
            if c.id == id_:
                return c
        raise KeyError(id_)

    def puntos(self) -> list[tuple[float, float, float]]:
        """Esquinas de todas las piezas: lo que la camara debe encuadrar."""
        return [p for c in self.piezas for p in c.esquinas_mm()]

    def caja(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        pts = self.puntos()
        return (
            tuple(min(p[i] for p in pts) for i in range(3)),  # type: ignore[return-value]
            tuple(max(p[i] for p in pts) for i in range(3)),
        )

    def claves(self) -> list[str]:
        return sorted({c.pieza.clave for c in self.piezas})

    def conexiones(self) -> list[Conexion]:
        return _conexiones(self.piezas)

    def resumen(self) -> str:
        (x0, y0, z0), (x1, y1, z1) = self.caja()
        sueltas = sum(1 for c in self.piezas if c.suelta)
        return (
            f"{self.nombre}: {_n(len(self.piezas), 'pieza', 'piezas')} "
            f"({len(self.piezas) - sueltas} en rejilla, {_n(sueltas, 'suelta', 'sueltas')}), "
            f"{_n(len(self.conexiones()), 'conexión', 'conexiones')}, "
            f"{_n(len(self.claves()), 'tipo de pieza', 'tipos de pieza')}, "
            f"caja {x1 - x0:.1f} x {y1 - y0:.1f} x {z1 - z0:.1f} mm"
        )


def _n(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


# --- Carga -------------------------------------------------------------------------

def cargar_escena(ruta: str | Path) -> Escena:
    """Lee y valida una escena JSON. Lanza :class:`EscenaInvalida`."""
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise EscenaInvalida([f"no existe el archivo {ruta}"], str(ruta)) from None
    except json.JSONDecodeError as e:
        raise EscenaInvalida(
            [f"JSON mal formado en la línea {e.lineno}, columna {e.colno}: {e.msg}"], str(ruta)
        ) from None
    return escena_desde_dict(datos, nombre_por_defecto=ruta.stem, origen=str(ruta))


def _es_numero(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _es_entero(v: object) -> bool:
    return _es_numero(v) and float(v).is_integer()  # type: ignore[arg-type]


def _leer_camara(datos: object, errores: list[str]) -> ConfigCamara:
    if datos is None:
        return ConfigCamara()
    if not isinstance(datos, dict):
        errores.append("'camara' debe ser un objeto JSON")
        return ConfigCamara()
    for k in sorted(set(datos) - _CLAVES_CAMARA):
        errores.append(f"clave desconocida {k!r} en 'camara' (válidas: {', '.join(sorted(_CLAVES_CAMARA))})")
    base = ConfigCamara()
    valores = {}
    rangos = {
        "azimut": (-360.0, 360.0),
        "elevacion": (2.0, 88.0),
        "lente": (12.0, 300.0),
        "margen": (0.0, 0.3),
        "apertura": (0.5, 64.0),
    }
    for k, (lo, hi) in rangos.items():
        if k not in datos or (k == "apertura" and datos[k] is None):
            continue
        v = datos[k]
        if not _es_numero(v) or not lo <= v <= hi:
            errores.append(f"'camara.{k}' debe ser un número entre {lo:g} y {hi:g}, no {v!r}")
        else:
            valores[k] = float(v)
    enfoque = datos.get("enfoque")
    if enfoque is not None and not isinstance(enfoque, str):
        errores.append(f"'camara.enfoque' debe ser el id de una pieza, no {enfoque!r}")
        enfoque = None
    return ConfigCamara(
        azimut=valores.get("azimut", base.azimut),
        elevacion=valores.get("elevacion", base.elevacion),
        lente=valores.get("lente", base.lente),
        margen=valores.get("margen", base.margen),
        enfoque=enfoque,
        apertura=valores.get("apertura"),
    )


def _leer_pieza(i: int, d: object, errores: list[str]) -> Colocacion | None:
    etiqueta = f"pieza #{i + 1}"
    if not isinstance(d, dict):
        errores.append(f"{etiqueta}: debe ser un objeto JSON, no {type(d).__name__}")
        return None
    if isinstance(d.get("id"), str) and d["id"].strip():
        etiqueta = f"pieza {d['id']!r}"
    elif "id" in d:
        errores.append(f"{etiqueta}: 'id' debe ser un texto no vacío")
    antes = len(errores)
    for k in sorted(set(d) - _CLAVES_PIEZA):
        errores.append(f"{etiqueta}: clave desconocida {k!r} (válidas: {', '.join(sorted(_CLAVES_PIEZA))})")

    pieza = None
    if "pieza" not in d:
        errores.append(f"{etiqueta}: falta 'pieza' (p. ej. \"ladrillo_2x4\")")
    else:
        try:
            pieza = pieza_por_clave(d["pieza"])
        except MedidaInvalida as e:
            errores.append(f"{etiqueta}: {e}")

    color = d.get("color")
    if color is None:
        errores.append(f"{etiqueta}: falta 'color'")
    elif color not in PALETA:
        errores.append(
            f"{etiqueta}: color desconocido {color!r}; disponibles: {', '.join(sorted(PALETA))}"
        )

    angulo = d.get("angulo")
    if angulo is not None and not _es_numero(angulo):
        errores.append(f"{etiqueta}: 'angulo' debe ser un número de grados, no {angulo!r}")
        angulo = None

    nivel = d.get("nivel", 0)
    if not _es_entero(nivel) or nivel < 0:
        errores.append(f"{etiqueta}: 'nivel' debe ser un entero >= 0 (en placas), no {nivel!r}")
        nivel = 0
    nivel = int(nivel)
    if angulo is not None and nivel != 0:
        errores.append(
            f"{etiqueta}: 'angulo' libre solo se admite en piezas sueltas en el suelo (nivel 0); "
            f"esta está en el nivel {nivel}. Usa 'rot' (0/90/180/270) para encajarla en la rejilla."
        )

    rot = d.get("rot", 0)
    if not _es_entero(rot) or int(rot) not in ROTACIONES:
        errores.append(f"{etiqueta}: 'rot' debe ser 0, 90, 180 o 270, no {rot!r}")
        rot = 0
    rot = int(rot)

    pos = d.get("pos")
    x = y = 0.0
    if not (isinstance(pos, list) and len(pos) == 2 and all(_es_numero(v) for v in pos)):
        errores.append(f"{etiqueta}: 'pos' debe ser [x, y] en studs, no {pos!r}")
    elif angulo is None and not all(_es_entero(v) for v in pos):
        errores.append(
            f"{etiqueta}: 'pos' debe ser entera en la rejilla de studs (recibido {pos}); "
            f"solo las piezas sueltas con 'angulo' admiten posiciones decimales"
        )
    else:
        x, y = float(pos[0]), float(pos[1])
        if angulo is None:
            x, y = int(x), int(y)

    if len(errores) > antes or pieza is None:
        return None
    id_ = d.get("id") or f"{pieza.clave}_{i + 1}"
    return Colocacion(
        id=id_, pieza=pieza, color=color, x=x, y=y, nivel=nivel, rot=rot,
        angulo=float(angulo) if angulo is not None else None,
    )


def escena_desde_dict(datos: object, nombre_por_defecto: str = "escena", origen: str = "la escena") -> Escena:
    errores: list[str] = []
    if not isinstance(datos, dict):
        raise EscenaInvalida(["el JSON debe ser un objeto con la lista 'piezas'"], origen)
    for k in sorted(set(datos) - _CLAVES_ESCENA):
        errores.append(f"clave desconocida {k!r} en la escena (válidas: {', '.join(sorted(_CLAVES_ESCENA))})")

    nombre = datos.get("nombre", nombre_por_defecto)
    if not isinstance(nombre, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", nombre):
        errores.append(f"'nombre' debe ser un identificador de archivo (letras, números, _ o -), no {nombre!r}")
        nombre = "escena"
    descripcion = datos.get("descripcion", "")
    if not isinstance(descripcion, str):
        errores.append("'descripcion' debe ser texto")
        descripcion = ""
    fondo = datos.get("fondo", "#EDEDEF")
    if not isinstance(fondo, str) or not _HEX_RE.match(fondo):
        errores.append(f"'fondo' debe ser un color hex como \"#EDEDEF\", no {fondo!r}")
        fondo = "#EDEDEF"

    camara = _leer_camara(datos.get("camara"), errores)

    lista = datos.get("piezas")
    if not isinstance(lista, list) or not lista:
        errores.append("'piezas' debe ser una lista con al menos una pieza")
        lista = []
    elif len(lista) > MAX_PIEZAS:
        errores.append(f"demasiadas piezas ({len(lista)}); el máximo es {MAX_PIEZAS}")
        lista = []

    piezas: list[Colocacion] = []
    vistos: set[str] = set()
    for i, d in enumerate(lista):
        c = _leer_pieza(i, d, errores)
        if c is None:
            continue
        if c.id in vistos:
            errores.append(f"pieza {c.id!r}: el id está repetido")
            continue
        vistos.add(c.id)
        piezas.append(c)

    if camara.enfoque is not None and camara.enfoque not in vistos:
        errores.append(f"'camara.enfoque' apunta a {camara.enfoque!r}, que no es el id de ninguna pieza")

    if errores:
        raise EscenaInvalida(errores, origen)

    escena = Escena(nombre=nombre, piezas=tuple(piezas), camara=camara, descripcion=descripcion, fondo=fondo)
    errores = validar(escena)
    if errores:
        raise EscenaInvalida(errores, origen)
    return escena


# --- Validacion fisica ---------------------------------------------------------------

def _separados(a: list[tuple[float, float]], b: list[tuple[float, float]], tol: float = 1e-6) -> bool:
    """Teorema del eje separador para dos poligonos convexos en planta."""
    for poly in (a, b):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            nx, ny = y1 - y2, x2 - x1
            pa = [nx * x + ny * y for x, y in a]
            pb = [nx * x + ny * y for x, y in b]
            escala = math.hypot(nx, ny)
            if max(pa) <= min(pb) + tol * escala or max(pb) <= min(pa) + tol * escala:
                return True
    return False


def _colisiones(piezas: tuple[Colocacion, ...]) -> list[str]:
    errores: list[str] = []
    ocupadas: dict[tuple[int, int, int], str] = {}
    reportadas: set[tuple[str, str]] = set()
    for c in piezas:
        if c.suelta:
            continue
        for celda in sorted(c.celdas()):
            otro = ocupadas.get(celda)
            if otro is None:
                ocupadas[celda] = c.id
            elif (otro, c.id) not in reportadas:
                reportadas.add((otro, c.id))
                x, y, z = celda
                errores.append(
                    f"la pieza {c.id!r} se solapa con {otro!r}: las dos ocupan la celda "
                    f"(x={x}, y={y}) en el nivel {z}"
                )
    # Piezas sueltas: interseccion de rectangulos girados si comparten altura.
    for i, a in enumerate(piezas):
        for b in piezas[i + 1:]:
            if not (a.suelta or b.suelta):
                continue
            if a.z_max <= b.z_min or b.z_max <= a.z_min:
                continue
            if not _separados(a.rectangulo_mm(), b.rectangulo_mm()):
                errores.append(
                    f"la pieza {b.id!r} se solapa con {a.id!r} (al menos una está girada con 'angulo'; "
                    f"sepáralas en planta)"
                )
    return errores


def _conexiones(piezas: tuple[Colocacion, ...]) -> list[Conexion]:
    """Pares (abajo, arriba) unidos por al menos un stud."""
    por_nivel: dict[int, list[Colocacion]] = {}
    for c in piezas:
        if not c.suelta:
            por_nivel.setdefault(c.nivel, []).append(c)
    out: list[Conexion] = []
    for abajo in piezas:
        if abajo.suelta or not abajo.pieza.con_studs:
            continue
        huella = abajo.huella_celdas()
        for arriba in por_nivel.get(abajo.nivel_superior, []):
            n = len(huella & arriba.huella_celdas())
            if n:
                out.append(Conexion(abajo.id, arriba.id, n))
    return out


def _soporte(piezas: tuple[Colocacion, ...], conexiones: list[Conexion]) -> list[str]:
    vecinos: dict[str, set[str]] = {c.id: set() for c in piezas}
    for cx in conexiones:
        vecinos[cx.abajo].add(cx.arriba)
        vecinos[cx.arriba].add(cx.abajo)
    anclados = {c.id for c in piezas if c.nivel == 0}
    cola = deque(anclados)
    while cola:
        actual = cola.popleft()
        for v in vecinos[actual]:
            if v not in anclados:
                anclados.add(v)
                cola.append(v)

    errores: list[str] = []
    baldosas_bajo: dict[str, list[str]] = {}
    for abajo in piezas:
        if abajo.suelta or abajo.pieza.con_studs:
            continue
        for arriba in piezas:
            if (not arriba.suelta and arriba.nivel == abajo.nivel_superior
                    and abajo.huella_celdas() & arriba.huella_celdas()):
                baldosas_bajo.setdefault(arriba.id, []).append(abajo.id)
    for c in piezas:
        if c.id in anclados:
            continue
        if not vecinos[c.id]:
            detalle = (
                f"ningún stud la sujeta: no hay piezas con studs justo debajo (nivel {c.nivel - 1}) "
                f"ni justo encima"
            )
            if c.id in baldosas_bajo:
                detalle += f"; {', '.join(repr(b) for b in baldosas_bajo[c.id])} es una baldosa y no tiene studs"
        else:
            detalle = (
                f"solo está unida a {', '.join(repr(v) for v in sorted(vecinos[c.id]))}, "
                f"y ese grupo tampoco llega al suelo"
            )
        errores.append(f"la pieza {c.id!r} (nivel {c.nivel}) está flotando: {detalle}")
    return errores


def validar(escena: Escena) -> list[str]:
    """Colisiones y soporte. Devuelve la lista de errores (vacia si es valida)."""
    errores = _colisiones(escena.piezas)
    errores += _soporte(escena.piezas, _conexiones(escena.piezas))
    return errores
