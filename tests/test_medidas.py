import math

import pytest

from bloques3d.medidas import (
    ALTURA_LADRILLO,
    CATALOGO,
    PASO,
    STUD_DIAMETRO,
    TUBO_DIAMETRO_EXT,
    MedidaInvalida,
    Pieza,
    pieza_por_clave,
    plan_pieza,
)


def test_ladrillo_2x4_medidas_reales():
    plan = plan_pieza(Pieza.ladrillo(2, 4))
    assert plan.exterior == (31.8, 15.8, 9.6)
    assert plan.altura_total == pytest.approx(11.3)
    assert len(plan.studs) == 8
    assert len(plan.tubos) == 3
    assert plan.barras == ()
    assert plan.cavidad == pytest.approx((29.4, 13.4, 8.6))
    assert plan.caja == ((-15.9, -7.9, 0.0), (15.9, 7.9, 11.3))


@pytest.mark.parametrize(
    "pieza, studs, tubos, barras",
    [
        (Pieza.ladrillo(1, 1), 1, 0, 0),
        (Pieza.ladrillo(1, 2), 2, 0, 1),
        (Pieza.ladrillo(1, 4), 4, 0, 3),
        (Pieza.ladrillo(2, 2), 4, 1, 0),
        (Pieza.ladrillo(2, 3), 6, 2, 0),
        (Pieza.ladrillo(2, 6), 12, 5, 0),
        (Pieza.placa(4, 4), 16, 9, 0),
        (Pieza.baldosa(2, 2), 0, 1, 0),
        (Pieza.baldosa(1, 2), 0, 0, 1),
        (Pieza.ladrillo(4, 1), 4, 0, 3),  # 1xN girado: barras a lo largo de Y
    ],
)
def test_recuento_de_studs_tubos_y_barras(pieza, studs, tubos, barras):
    plan = plan_pieza(pieza)
    assert (len(plan.studs), len(plan.tubos), len(plan.barras)) == (studs, tubos, barras)


def test_studs_en_el_centro_de_cada_celda():
    plan = plan_pieza(Pieza.ladrillo(2, 4))
    xs = sorted({x for x, _ in plan.studs})
    ys = sorted({y for _, y in plan.studs})
    assert xs == [-12.0, -4.0, 4.0, 12.0]
    assert ys == [-4.0, 4.0]


def test_tubo_tangente_a_los_cuatro_studs_que_lo_rodean():
    # El tubo va en el cruce de 4 studs y los toca: distancia entre centros
    # = radio del tubo + radio del stud (con 2 micras de holgura por redondeo).
    distancia = math.hypot(PASO / 2, PASO / 2)
    holgura = distancia - (TUBO_DIAMETRO_EXT / 2 + STUD_DIAMETRO / 2)
    assert 0 <= holgura < 0.01


def test_placa_y_baldosa():
    assert Pieza.placa(2, 4).altura == pytest.approx(3.2)
    assert Pieza.placa(2, 4).altura_total == pytest.approx(4.9)
    assert Pieza.baldosa(2, 2).altura_total == pytest.approx(3.2)  # sin studs
    assert Pieza.ladrillo(2, 2).altura == pytest.approx(ALTURA_LADRILLO)


@pytest.mark.parametrize(
    "args",
    [(0, 4, 3), (2, -1, 3), (2, 4, 0), (2.5, 4, 3), (True, 4, 3), (2, 40, 3), ("2", 4, 3)],
)
def test_rechaza_tamanos_invalidos(args):
    with pytest.raises(MedidaInvalida):
        Pieza(*args)


def test_rechaza_tipo_desconocido():
    with pytest.raises(MedidaInvalida, match="tipo de pieza desconocido"):
        Pieza(2, 4, 3, "rueda")


def test_plan_pieza_exige_una_pieza():
    with pytest.raises(MedidaInvalida):
        plan_pieza("ladrillo_2x4")  # type: ignore[arg-type]


def test_pieza_por_clave_acepta_cualquier_tamano():
    p = pieza_por_clave("placa_6x8")
    assert (p.tipo, p.ancho, p.largo, p.placas) == ("placa", 6, 8, 1)
    assert pieza_por_clave(" Ladrillo_1x3 ").clave == "ladrillo_1x3"


@pytest.mark.parametrize("clave", ["ladrillo_2", "cubo_2x2", "placa_0x4", "ladrillo_2x99", 42])
def test_pieza_por_clave_rechaza(clave):
    with pytest.raises(MedidaInvalida):
        pieza_por_clave(clave)


def test_catalogo_de_serie():
    esperado = {
        "ladrillo_1x1", "ladrillo_1x2", "ladrillo_1x4", "ladrillo_2x2", "ladrillo_2x3", "ladrillo_2x4",
        "ladrillo_2x6", "placa_2x4", "placa_4x4", "baldosa_2x2",
    }
    assert esperado <= set(CATALOGO)
    for clave, pieza in CATALOGO.items():
        assert pieza.clave == clave
        assert pieza_por_clave(clave) == pieza
