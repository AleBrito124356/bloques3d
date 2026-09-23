"""Encuadre automatico de la camara (Python puro).

Dada una orientacion (azimut y elevacion), una lente y un aspecto, calcula
la posicion de camara **mas cercana** que deja todos los puntos dentro del
encuadre con un margen. Con la orientacion fija, cada punto y cada borde del
encuadre dan una restriccion lineal sobre la posicion, y el optimo tiene
solucion cerrada (ver :func:`encuadrar`).

Las coordenadas de encuadre siguen la convencion de
``bpy_extras.object_utils.world_to_camera_view``: ``u`` y ``v`` van de 0 a 1
de izquierda a derecha y de abajo a arriba.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

Vec = tuple[float, float, float]
SENSOR_MM = 36.0


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> Vec:
    n = math.sqrt(_dot(a, a))
    if n == 0:
        raise ValueError("vector nulo")
    return _mul(a, 1.0 / n)


def direccion_camara(azimut: float, elevacion: float) -> Vec:
    """Vector unitario del objetivo hacia la camara.

    ``azimut`` = 0 pone la camara delante (en -Y) y crece hacia +X;
    ``elevacion`` se mide desde el horizonte.
    """
    az, el = math.radians(azimut), math.radians(elevacion)
    return (math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))


def base_camara(azimut: float, elevacion: float) -> tuple[Vec, Vec, Vec]:
    """(derecha, arriba, adelante) de una camara sin alabeo."""
    if not -89.9 <= elevacion <= 89.9:
        raise ValueError("la elevacion debe estar entre -89.9 y 89.9 grados")
    adelante = _mul(direccion_camara(azimut, elevacion), -1.0)
    derecha = _norm(_cross(adelante, (0.0, 0.0, 1.0)))
    arriba = _cross(derecha, adelante)
    return derecha, arriba, adelante


def tangentes(lente: float, aspecto: float, sensor: float = SENSOR_MM) -> tuple[float, float]:
    """Tangentes de medio angulo (horizontal, vertical).

    Igual que el ajuste de sensor ``AUTO`` de Blender: el sensor cubre el lado
    mas largo de la imagen.
    """
    if lente <= 0 or aspecto <= 0 or sensor <= 0:
        raise ValueError("lente, aspecto y sensor deben ser positivos")
    t = (sensor / 2.0) / lente
    return (t, t / aspecto) if aspecto >= 1.0 else (t * aspecto, t)


@dataclass(frozen=True)
class Encuadre:
    posicion: Vec
    derecha: Vec
    arriba: Vec
    adelante: Vec
    lente: float
    aspecto: float
    sensor: float = SENSOR_MM

    def camara_local(self, p: Vec) -> Vec:
        d = _sub(p, self.posicion)
        return (_dot(d, self.derecha), _dot(d, self.arriba), _dot(d, self.adelante))

    def proyectar(self, p: Vec) -> Vec:
        """(u, v, profundidad) como ``world_to_camera_view``."""
        x, y, z = self.camara_local(p)
        tx, ty = tangentes(self.lente, self.aspecto, self.sensor)
        if z <= 0:
            return (float("nan"), float("nan"), z)
        return (0.5 + 0.5 * x / (z * tx), 0.5 + 0.5 * y / (z * ty), z)

    def matriz_rotacion(self) -> tuple[Vec, Vec, Vec]:
        """Filas de la matriz 3x3 del objeto camara (columnas X, Y, Z locales).

        La camara de Blender mira hacia su -Z local con +Y hacia arriba.
        """
        cols = (self.derecha, self.arriba, _mul(self.adelante, -1.0))
        return tuple(tuple(cols[c][r] for c in range(3)) for r in range(3))  # type: ignore[return-value]


def encuadrar(
    puntos: list[Vec],
    azimut: float,
    elevacion: float,
    lente: float,
    aspecto: float,
    margen: float = 0.07,
    sensor: float = SENSOR_MM,
) -> Encuadre:
    """Posicion de camara mas cercana con todos los ``puntos`` dentro del margen.

    En coordenadas de camara (x derecha, y arriba, z profundidad) un punto
    ``q`` queda dentro si ``|x_q - x_c| <= a (z_q - z_c)`` con
    ``a = (1 - 2 margen) tan(fov/2)``, y lo mismo en vertical. Para cada eje:
    ``A = max(x - a z)``, ``B = max(-x - a z)`` y el optimo es
    ``x_c = (A - B) / 2``, ``z_c = -(A + B) / (2 a)``. Se toma la ``z_c`` mas
    atrasada de los dos ejes, asi el contenido queda centrado en ambos.
    """
    if not puntos:
        raise ValueError("no hay puntos que encuadrar")
    if not 0.0 <= margen < 0.5:
        raise ValueError("el margen debe estar en [0, 0.5)")
    derecha, arriba, adelante = base_camara(azimut, elevacion)
    tx, ty = tangentes(lente, aspecto, sensor)
    a, b = (1 - 2 * margen) * tx, (1 - 2 * margen) * ty
    loc = [(_dot(p, derecha), _dot(p, arriba), _dot(p, adelante)) for p in puntos]
    A = max(x - a * z for x, _, z in loc)
    B = max(-x - a * z for x, _, z in loc)
    C = max(y - b * z for _, y, z in loc)
    D = max(-y - b * z for _, y, z in loc)
    xc, yc = (A - B) / 2.0, (C - D) / 2.0
    zc = min(-(A + B) / (2 * a), -(C + D) / (2 * b))
    # En el eje que no fija la distancia, (A - B) / 2 no centra exactamente
    # por la perspectiva: se reequilibra a la distancia final. Igualar los dos
    # lados solo puede bajar el mayor, asi que el margen se sigue cumpliendo.
    xc = _centrar([(x, z) for x, _, z in loc], zc, xc)
    yc = _centrar([(y, z) for _, y, z in loc], zc, yc)
    posicion = _add(_add(_mul(derecha, xc), _mul(arriba, yc)), _mul(adelante, zc))
    return Encuadre(posicion, derecha, arriba, adelante, lente, aspecto, sensor)


def _centrar(pares: list[tuple[float, float]], zc: float, inicial: float) -> float:
    """Posicion lateral que iguala el mayor desborde a cada lado (biseccion)."""
    def desequilibrio(c: float) -> float:
        return max((x - c) / (z - zc) for x, z in pares) - max((c - x) / (z - zc) for x, z in pares)

    ancho = max(abs(x - inicial) for x, _ in pares) + 1.0
    lo, hi = inicial - ancho, inicial + ancho
    for _ in range(80):  # desequilibrio() es decreciente en c
        mid = (lo + hi) / 2
        if desequilibrio(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def distancia_orbita(
    puntos: list[Vec],
    centro: Vec,
    elevacion: float,
    lente: float,
    aspecto: float,
    margen: float = 0.07,
    sensor: float = SENSOR_MM,
    muestras: int = 360,
) -> float:
    """Distancia minima al ``centro`` para una camara que orbita mirandolo.

    Para cada azimut muestreado, un punto necesita
    ``s >= |x| / a - z`` (y lo mismo en vertical), con x, z relativas al
    centro. Se devuelve el maximo sobre todos los azimuts y puntos.
    """
    tx, ty = tangentes(lente, aspecto, sensor)
    a, b = (1 - 2 * margen) * tx, (1 - 2 * margen) * ty
    rel = [_sub(p, centro) for p in puntos]
    s = 0.0
    for i in range(muestras):
        derecha, arriba, adelante = base_camara(360.0 * i / muestras, elevacion)
        for p in rel:
            x, y, z = _dot(p, derecha), _dot(p, arriba), _dot(p, adelante)
            s = max(s, abs(x) / a - z, abs(y) / b - z)
    # El muestreo angular puede quedarse corto entre dos muestras: +0.5 %.
    return s * 1.005
