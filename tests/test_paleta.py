import pytest

from bloques3d.paleta import PALETA, color, srgb_a_lineal


def test_srgb_a_lineal_puntos_conocidos():
    assert srgb_a_lineal(0.0) == 0.0
    assert srgb_a_lineal(1.0) == pytest.approx(1.0)
    assert srgb_a_lineal(0.5) == pytest.approx(0.214041, abs=1e-6)
    with pytest.raises(ValueError):
        srgb_a_lineal(1.5)


def test_paleta():
    assert color("azul").srgb == pytest.approx((0, 0x55 / 255, 0xBF / 255))
    assert all(0 < c.rugosidad < 1 for c in PALETA.values())
    assert PALETA["transparente"].transparente
    with pytest.raises(KeyError, match="color desconocido"):
        color("morado")
