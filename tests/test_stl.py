import pytest

from tests.stl import escribir_stl_binario, leer_stl


CUBO = [
    ((0, 0, 0), (1, 1, 0), (1, 0, 0)), ((0, 0, 0), (0, 1, 0), (1, 1, 0)),
    ((0, 0, 1), (1, 0, 1), (1, 1, 1)), ((0, 0, 1), (1, 1, 1), (0, 1, 1)),
    ((0, 0, 0), (1, 0, 0), (1, 0, 1)), ((0, 0, 0), (1, 0, 1), (0, 0, 1)),
    ((0, 1, 0), (1, 1, 1), (1, 1, 0)), ((0, 1, 0), (0, 1, 1), (1, 1, 1)),
    ((0, 0, 0), (0, 0, 1), (0, 1, 1)), ((0, 0, 0), (0, 1, 1), (0, 1, 0)),
    ((1, 0, 0), (1, 1, 0), (1, 1, 1)), ((1, 0, 0), (1, 1, 1), (1, 0, 1)),
]


def test_lector_stl_binario_cubo_estanco(tmp_path):
    ruta = tmp_path / "cubo.stl"
    escribir_stl_binario(ruta, CUBO)
    m = leer_stl(ruta)
    assert len(m) == 12
    assert m.dimensiones() == pytest.approx((1, 1, 1))
    assert m.aristas_no_cerradas() == 0
    assert m.triangulos_degenerados() == 0


def test_lector_stl_detecta_agujero(tmp_path):
    ruta = tmp_path / "abierto.stl"
    escribir_stl_binario(ruta, CUBO[:-1])
    assert leer_stl(ruta).aristas_no_cerradas() == 3


def test_lector_stl_ascii(tmp_path):
    ruta = tmp_path / "tri.stl"
    ruta.write_text(
        "solid t\n facet normal 0 0 1\n  outer loop\n   vertex 0 0 0\n   vertex 2 0 0\n"
        "   vertex 0 3 0\n  endloop\n endfacet\nendsolid t\n", encoding="ascii")
    m = leer_stl(ruta)
    assert len(m) == 1 and m.dimensiones() == pytest.approx((2, 3, 0))
