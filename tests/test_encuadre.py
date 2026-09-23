import math
import random

import pytest

from bloques3d.encuadre import (
    base_camara,
    direccion_camara,
    distancia_orbita,
    encuadrar,
    tangentes,
)
from bloques3d.escena import cargar_escena
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def nube(n, semilla, escala=40.0):
    rnd = random.Random(semilla)
    return [(rnd.uniform(-escala, escala), rnd.uniform(-escala, escala), rnd.uniform(0, escala)) for _ in range(n)]


def test_base_ortonormal_y_sin_alabeo():
    for az in (0, 33, 90, 200, -45):
        for el in (5, 30, 70):
            d, a, f = base_camara(az, el)
            for v in (d, a, f):
                assert math.isclose(sum(c * c for c in v), 1.0, abs_tol=1e-12)
            assert abs(sum(x * y for x, y in zip(d, a))) < 1e-12
            assert abs(d[2]) < 1e-12          # el eje "derecha" es horizontal: horizonte recto
            assert a[2] > 0                   # "arriba" apunta hacia arriba


def test_azimut_cero_mira_desde_delante():
    x, y, z = direccion_camara(0, 0)
    assert (x, y, z) == pytest.approx((0, -1, 0))


def test_tangentes_como_sensor_auto_de_blender():
    tx, ty = tangentes(50, 16 / 9)
    assert tx == pytest.approx(18 / 50)
    assert ty == pytest.approx(18 / 50 * 9 / 16)
    tx, ty = tangentes(50, 9 / 16)            # vertical: el sensor cubre el alto
    assert ty == pytest.approx(18 / 50)


@pytest.mark.parametrize("semilla", range(12))
def test_todos_los_puntos_quedan_dentro_del_margen(semilla):
    rnd = random.Random(semilla)
    pts = nube(60, semilla)
    az, el = rnd.uniform(-180, 180), rnd.uniform(8, 75)
    lente, aspecto, margen = rnd.choice([35, 50, 70, 100]), rnd.choice([16 / 9, 1.0, 4 / 5, 21 / 9]), rnd.uniform(0, 0.2)
    enc = encuadrar(pts, az, el, lente, aspecto, margen)
    us, vs = [], []
    for p in pts:
        u, v, prof = enc.proyectar(p)
        assert prof > 0
        us.append(u)
        vs.append(v)
    eps = 1e-9
    assert min(us) >= margen - eps and max(us) <= 1 - margen + eps
    assert min(vs) >= margen - eps and max(vs) <= 1 - margen + eps
    # Es el encuadre mas cercano: al menos un eje toca el margen por los dos lados.
    toca_u = math.isclose(min(us), margen, abs_tol=1e-7) and math.isclose(max(us), 1 - margen, abs_tol=1e-7)
    toca_v = math.isclose(min(vs), margen, abs_tol=1e-7) and math.isclose(max(vs), 1 - margen, abs_tol=1e-7)
    assert toca_u or toca_v


def test_contenido_centrado():
    enc = encuadrar(nube(40, 99), 30, 30, 70, 16 / 9, 0.05)
    us = [enc.proyectar(p)[0] for p in nube(40, 99)]
    assert (min(us) + max(us)) / 2 == pytest.approx(0.5, abs=1e-9)


def test_escena_trio_encuadrada():
    e = cargar_escena(RAIZ / "escenas" / "trio.json")
    c = e.camara
    enc = encuadrar(e.puntos(), c.azimut, c.elevacion, c.lente, 16 / 9, c.margen)
    for p in e.puntos():
        u, v, _ = enc.proyectar(p)
        assert c.margen - 1e-9 <= u <= 1 - c.margen + 1e-9
        assert c.margen - 1e-9 <= v <= 1 - c.margen + 1e-9


def test_matriz_rotacion_es_de_camara_blender():
    enc = encuadrar(nube(10, 1), 30, 30, 50, 1.5)
    filas = enc.matriz_rotacion()
    # columna Z local = -adelante (la camara mira hacia su -Z)
    assert tuple(filas[i][2] for i in range(3)) == pytest.approx(tuple(-c for c in enc.adelante))
    assert tuple(filas[i][1] for i in range(3)) == pytest.approx(enc.arriba)


def test_distancia_orbita_cubre_todos_los_azimuts():
    pts = nube(50, 5)
    centro = (0.0, 0.0, 20.0)
    s = distancia_orbita(pts, centro, 30, 60, 16 / 9, 0.05)
    for az in range(0, 360, 7):
        d, a, f = base_camara(az + 0.5, 30)   # azimuts que no estaban en el muestreo
        cam = tuple(centro[i] - f[i] * s for i in range(3))
        tx, ty = tangentes(60, 16 / 9)
        for p in pts:
            rel = tuple(p[i] - cam[i] for i in range(3))
            x = sum(rel[i] * d[i] for i in range(3))
            y = sum(rel[i] * a[i] for i in range(3))
            z = sum(rel[i] * f[i] for i in range(3))
            assert z > 0
            assert abs(x / (z * tx)) <= 1 - 2 * 0.05 + 1e-6
            assert abs(y / (z * ty)) <= 1 - 2 * 0.05 + 1e-6


@pytest.mark.parametrize("kw", [{"margen": 0.5}, {"lente": 0}, {"elevacion": 90}])
def test_parametros_invalidos(kw):
    args = {"azimut": 0, "elevacion": 30, "lente": 50, "aspecto": 1.0, "margen": 0.1, **kw}
    with pytest.raises(ValueError):
        encuadrar(nube(5, 0), **args)


def test_sin_puntos():
    with pytest.raises(ValueError):
        encuadrar([], 0, 30, 50, 1.0)
