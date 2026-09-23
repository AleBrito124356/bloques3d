import json
from pathlib import Path

import pytest

from bloques3d.escena import EscenaInvalida, cargar_escena, escena_desde_dict

RAIZ = Path(__file__).resolve().parents[1]


def escena(*piezas, **extra):
    return escena_desde_dict({"nombre": "prueba", "piezas": list(piezas), **extra})


def ladrillo(id_, pos, nivel=0, **kw):
    return {"id": id_, "pieza": "ladrillo_2x4", "color": "azul", "pos": pos, "nivel": nivel, **kw}


def errores_de(*piezas, **extra) -> list[str]:
    with pytest.raises(EscenaInvalida) as exc:
        escena(*piezas, **extra)
    return exc.value.errores


@pytest.mark.parametrize("ruta", sorted((RAIZ / "escenas").glob("*.json")), ids=lambda p: p.name)
def test_las_escenas_incluidas_son_validas(ruta):
    e = cargar_escena(ruta)
    assert e.nombre == ruta.stem
    assert e.piezas


def test_trio_es_el_plano_original_bien_hecho():
    e = cargar_escena(RAIZ / "escenas" / "trio.json")
    assert [c.id for c in e.piezas] == ["azul", "blanco", "rojo"]
    (con,) = e.conexiones()
    assert (con.abajo, con.arriba, con.studs) == ("azul", "blanco", 2)
    blanco = e.por_id("blanco")
    assert blanco.z_min == pytest.approx(9.6)  # justo encima del azul, ni un micrometro de mas
    assert e.por_id("azul").z_min == 0 and e.por_id("rojo").z_min == 0
    assert e.por_id("rojo").suelta


def test_casita_usa_placas_baldosas_y_piezas_1xN():
    e = cargar_escena(RAIZ / "escenas" / "casita.json")
    tipos = {c.pieza.tipo for c in e.piezas}
    assert tipos == {"ladrillo", "placa", "baldosa"}
    assert any(c.pieza.ancho == 1 for c in e.piezas)
    assert any(c.rot == 90 for c in e.piezas)
    assert len(e.conexiones()) >= 40


def test_solape_rechazado_con_nombre_de_pieza_y_celda():
    errores = errores_de(ladrillo("a", [0, 0]), ladrillo("b", [3, 1]))
    assert len(errores) == 1
    assert "'b' se solapa con 'a'" in errores[0]
    assert "(x=3, y=1) en el nivel 0" in errores[0]


def test_pieza_flotante_rechazada():
    errores = errores_de(ladrillo("suelo", [0, 0]), ladrillo("nube", [10, 10], nivel=3))
    assert len(errores) == 1
    assert "'nube' (nivel 3) está flotando" in errores[0]


def test_pieza_encima_con_un_nivel_de_hueco_flota():
    # 'b' empieza en el nivel 4, pero 'a' acaba en el 3: hay 1 placa de aire.
    errores = errores_de(ladrillo("a", [0, 0]), ladrillo("b", [0, 0], nivel=4))
    assert "'b' (nivel 4) está flotando" in errores[0]


def test_una_sola_fila_de_studs_basta_para_sujetar():
    e = escena(ladrillo("a", [0, 0]), ladrillo("b", [3, 1], nivel=3))
    (con,) = e.conexiones()
    assert con.studs == 1


def test_sujeta_desde_arriba_si_el_grupo_llega_al_suelo():
    # 'colgada' no apoya sobre nada, pero el puente que tiene encima si llega al suelo.
    e = escena(
        ladrillo("pilar_izq", [0, 0]),
        ladrillo("pilar_der", [8, 0]),
        {"id": "puente", "pieza": "placa_2x12", "color": "gris_claro", "pos": [0, 0], "nivel": 3},
        {"id": "colgada", "pieza": "placa_2x2", "color": "rojo", "pos": [5, 0], "nivel": 2},
    )
    assert e.por_id("colgada").nivel == 2
    assert {(c.abajo, c.arriba) for c in e.conexiones()} == {
        ("pilar_izq", "puente"), ("pilar_der", "puente"), ("colgada", "puente")}


def test_una_baldosa_no_sujeta_lo_de_encima():
    errores = errores_de(
        {"id": "baldosa", "pieza": "baldosa_2x2", "color": "gris_claro", "pos": [0, 0]},
        {"id": "encima", "pieza": "ladrillo_2x2", "color": "rojo", "pos": [0, 0], "nivel": 1},
    )
    assert "'encima' (nivel 1) está flotando" in errores[0]
    assert "'baldosa' es una baldosa y no tiene studs" in errores[0]


def test_grupo_flotante_se_explica():
    errores = errores_de(
        ladrillo("suelo", [0, 0]),
        ladrillo("isla_a", [20, 0], nivel=6),
        ladrillo("isla_b", [20, 0], nivel=9),
    )
    assert len(errores) == 2
    assert any("solo está unida a 'isla_a'" in e for e in errores)


def test_rotacion_90_cambia_la_huella():
    e = escena({"id": "g", "pieza": "ladrillo_2x4", "color": "rojo", "pos": [0, 0], "rot": 90})
    (c,) = e.piezas
    assert c.huella == (2, 4)
    assert c.centro_mm == (8.0, 16.0, 0.0)
    assert c.huella_celdas() == {(x, y) for x in range(2) for y in range(4)}


def test_pieza_suelta_con_angulo_libre():
    e = escena(ladrillo("a", [0, 0]), {"id": "r", "pieza": "ladrillo_2x4", "color": "rojo",
                                       "pos": [6.5, -3.25], "angulo": 17})
    r = e.por_id("r")
    assert r.suelta and r.giro_grados == 17
    assert r.centro_mm == (68.0, -18.0, 0.0)


def test_pieza_suelta_que_pisa_otra_se_rechaza():
    errores = errores_de(
        ladrillo("a", [0, 0]),
        {"id": "r", "pieza": "ladrillo_2x4", "color": "rojo", "pos": [1.5, 0.5], "angulo": 30},
    )
    assert "'r' se solapa con 'a'" in errores[0]


def test_angulo_libre_solo_en_el_suelo():
    errores = errores_de(ladrillo("a", [0, 0]), ladrillo("b", [0, 0], nivel=3, angulo=5))
    assert any("solo se admite en piezas sueltas en el suelo" in e for e in errores)


@pytest.mark.parametrize(
    "cambio, fragmento",
    [
        ({"rot": 45}, "'rot' debe ser 0, 90, 180 o 270"),
        ({"color": "morado"}, "color desconocido 'morado'"),
        ({"pieza": "ladrillo_2x"}, "pieza desconocida"),
        ({"pos": [0.5, 0]}, "'pos' debe ser entera"),
        ({"pos": [1]}, "'pos' debe ser [x, y]"),
        ({"nivel": -1}, "'nivel' debe ser un entero >= 0"),
        ({"nivle": 3}, "clave desconocida 'nivle'"),
    ],
)
def test_errores_de_formato_en_espanol(cambio, fragmento):
    pieza = {**ladrillo("x", [0, 0]), **cambio}
    errores = errores_de(pieza)
    assert any(fragmento in e and "'x'" in e for e in errores), errores


def test_junta_todos_los_errores_de_una_vez():
    errores = errores_de(
        {"id": "a", "pieza": "ladrillo_9x", "color": "azul", "pos": [0, 0]},
        {"id": "b", "pieza": "ladrillo_2x2", "color": "fucsia", "pos": [0, 0]},
    )
    assert len(errores) == 2


def test_ids_repetidos_y_enfoque_inexistente():
    errores = errores_de(ladrillo("a", [0, 0]), ladrillo("a", [5, 0]), camara={"enfoque": "zeta"})
    assert any("id está repetido" in e for e in errores)
    assert any("'zeta'" in e for e in errores)


def test_camara_fuera_de_rango():
    errores = errores_de(ladrillo("a", [0, 0]), camara={"elevacion": 95, "lente": 2})
    assert len(errores) == 2


def test_json_mal_formado_da_linea_y_columna(tmp_path):
    ruta = tmp_path / "rota.json"
    ruta.write_text('{"piezas": [\n  {"id": "a",,}\n]}', encoding="utf-8")
    with pytest.raises(EscenaInvalida, match="línea 2"):
        cargar_escena(ruta)


def test_archivo_inexistente(tmp_path):
    with pytest.raises(EscenaInvalida, match="no existe"):
        cargar_escena(tmp_path / "nada.json")


def test_nombre_por_defecto_es_el_del_archivo(tmp_path):
    ruta = tmp_path / "mi_escena.json"
    ruta.write_text(json.dumps({"piezas": [ladrillo("a", [0, 0])]}), encoding="utf-8")
    assert cargar_escena(ruta).nombre == "mi_escena"


def test_puntos_de_encuadre_incluyen_studs():
    e = escena(ladrillo("a", [0, 0]))
    (x0, y0, z0), (x1, y1, z1) = e.caja()
    assert (x0, y0, z0) == pytest.approx((0.1, 0.1, 0.0))
    assert (x1, y1, z1) == pytest.approx((31.9, 15.9, 11.3))
