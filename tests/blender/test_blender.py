"""Pruebas de integracion con Blender real.

Lanzan ``blender --background --factory-startup`` (nunca la sesion con
interfaz del usuario) y se saltan solas si no hay Blender instalado. Todo es
local y sin red: no hay claves ni servicios externos.
"""
from __future__ import annotations

import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from bloques3d.cli import ARGS_SEGUROS, BlenderNoEncontrado, buscar_blender
from tests.stl import leer_stl

RAIZ = Path(__file__).resolve().parents[2]
AQUI = Path(__file__).resolve().parent

pytestmark = pytest.mark.blender


@pytest.fixture(scope="session")
def blender() -> Path:
    try:
        return buscar_blender()
    except BlenderNoEncontrado as e:
        pytest.skip(f"Blender no disponible: {e}")


def cli(*args, esperado: int = 0) -> subprocess.CompletedProcess:
    proc = subprocess.run([sys.executable, "-m", "bloques3d", *map(str, args)], cwd=RAIZ, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=900)
    assert proc.returncode == esperado, f"código {proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    return proc


def en_blender(blender: Path, script: Path, *args, blend: Path | None = None) -> dict:
    cmd = [str(blender), *ARGS_SEGUROS, *([str(blend)] if blend else []), "--python-exit-code", "1",
           "--python", str(script), "--", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=900)
    linea = next((l for l in proc.stdout.splitlines() if l.startswith("RESULTADO_PRUEBA ")), None)
    assert proc.returncode == 0 and linea, f"código {proc.returncode}\n{proc.stdout[-3000:]}\n{proc.stderr[-3000:]}"
    return json.loads(linea.split(" ", 1)[1])


def comprobar(blend: Path, *extra) -> dict:
    proc = subprocess.run([sys.executable, "-m", "bloques3d", "comprobar", str(blend), "--json", *extra],
                          cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=900)
    assert proc.returncode in (0, 1), proc.stderr
    informe = json.loads(proc.stdout)
    assert informe["ok"] == (proc.returncode == 0)
    return informe


def tamano_png(ruta: Path) -> tuple[int, int]:
    cab = ruta.read_bytes()[:24]
    assert cab[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", cab[16:24])


def leer_glb(ruta: Path) -> dict:
    datos = ruta.read_bytes()
    magia, version, largo = struct.unpack_from("<4sII", datos, 0)
    assert (magia, version, largo) == (b"glTF", 2, len(datos))
    largo_json, tipo = struct.unpack_from("<I4s", datos, 12)
    assert tipo == b"JSON"
    return json.loads(datos[20:20 + largo_json])


@pytest.fixture(scope="session")
def trio(blender, tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("trio")
    cli("render", "escenas/trio.json", "--res", "640x360", "--muestras", "16", "--salida", d,
        "--stl", d / "stl", "--glb", d / "trio.glb", "--jpeg", "--blender", blender)
    return d


# --- Piezas --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def piezas(blender) -> dict:
    return en_blender(blender, AQUI / "comprobar_piezas.py")


def test_cada_pieza_del_catalogo_es_cerrada_y_mide_lo_que_dice(piezas):
    from bloques3d.medidas import CATALOGO, plan_pieza

    assert set(piezas["piezas"]) == set(CATALOGO)
    for clave, r in piezas["piezas"].items():
        plan = plan_pieza(CATALOGO[clave])
        esperado = [plan.exterior[0], plan.exterior[1], plan.altura_total]
        assert r["no_manifold_base"] == 0, clave
        assert r["no_manifold_evaluada"] == 0, clave
        assert r["dim"] == pytest.approx(esperado, abs=0.01), clave
        assert r["z_min"] == 0.0, clave                      # apoyada en el suelo, exacto
        assert r["fuera_de_la_caja"] < 1e-4, clave           # el bisel no saca nada fuera


@pytest.mark.parametrize("nombre", [
    "2x4_sobre_2x4_desplazado_2_studs", "2x4_sobre_2x4_como_trio", "2x4_girado_sobre_2x4",
    "1x4_sobre_1x4_desplazado", "1x4_sobre_1x1", "placa_4x4_sobre_2x2", "baldosa_sobre_placa",
    "2x6_sobre_dos_2x2",
])
def test_apilados_encajan_sin_atravesarse(piezas, nombre):
    r = piezas["apilados"][nombre]
    assert r["ok"], r["fallos"]
    assert r["contactos"], "las piezas deberían tocarse"
    for c in r["contactos"]:
        assert c["pares_1um"] == 0              # con 1 micra de aire no se cruza ninguna cara
        assert c["vertices_enterrados"] == 0    # ningún vértice dentro del sólido de la otra
        assert c["pares_contacto"] > 0          # y en contacto exacto sí se tocan (apoyo real)


def test_el_comprobador_detecta_los_fallos_de_la_escena_original(blender):
    """El .blend original (historial/) flota 4.8 mm, se atraviesa y se sale del encuadre."""
    informe = comprobar(RAIZ / "historial" / "bloques_original.blend",
                        "--piezas", "Brick_Blue,Brick_White,Brick_Red", "--suelo", "Brick_Blue,Brick_Red",
                        "--blender", blender)
    assert not informe["ok"]
    # Aquella escena usaba 1 unidad = 10 mm: 0.48 unidades = 4.8 mm de hueco bajo cada ladrillo.
    assert informe["suelo"] == {"Brick_Blue": 0.48, "Brick_Red": 0.48}
    (cruce,) = [c for c in informe["contactos"] if c["arriba"] == "Brick_White"]
    assert cruce["pares_1um"] > 0 and cruce["vertices_enterrados"] > 100
    assert informe["encuadre"]["v"][1] > 1.0 and informe["encuadre"]["v"][0] < 0.0


# --- Escena trio de punta a punta ---------------------------------------------------------

def test_trio_genera_blend_png_y_jpg(trio):
    assert (trio / "trio.blend").is_file()
    assert (trio / "trio.blend").stat().st_size < 1_000_000
    assert tamano_png(trio / "trio.png") == (640, 360)
    assert (trio / "trio.jpg").read_bytes()[:3] == b"\xff\xd8\xff"


def test_trio_geometria_en_el_blend(trio, blender):
    informe = comprobar(trio / "trio.blend", "--margen", "0.03", "--blender", blender)
    assert informe["ok"], informe["fallos"]
    u0, u1 = informe["encuadre"]["u"]
    v0, v1 = informe["encuadre"]["v"]
    assert 0.03 <= u0 and u1 <= 0.97 and 0.03 <= v0 and v1 <= 0.97
    assert informe["suelo"] == {"azul": 0.0, "rojo": 0.0}
    (c,) = informe["contactos"]
    assert (c["abajo"], c["arriba"]) == ("azul", "blanco")
    assert c["pares_1um"] == 0 and c["vertices_enterrados"] == 0


def test_regenerar_no_deja_copias_blend1(blender, tmp_path):
    for _ in range(2):
        cli("render", "escenas/trio.json", "--sin-render", "--salida", tmp_path, "--blender", blender)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["trio.blend"]


def test_trio_blend_portable(trio, blender):
    datos = en_blender(blender, AQUI / "inspeccionar_blend.py", blend=trio / "trio.blend")
    assert datos["render_filepath"] == "//trio.png"         # ruta relativa al .blend
    assert datos["scale_length"] == pytest.approx(0.001)    # 1 unidad = 1 mm
    assert datos["length_unit"] == "MILLIMETERS"
    assert datos["piezas"] == {"azul": "ladrillo_2x4", "blanco": "ladrillo_2x4", "rojo": "ladrillo_2x4"}
    assert datos["rutas_absolutas"] == []


def test_trio_stl_en_milimetros_y_estanco(trio):
    stl = leer_stl(trio / "stl" / "ladrillo_2x4.stl")
    assert len(stl) > 500
    assert stl.dimensiones() == pytest.approx((31.8, 15.8, 11.3), abs=0.01)
    assert stl.caja()[0][2] == pytest.approx(0.0, abs=1e-6)
    assert stl.aristas_no_cerradas() == 0
    assert stl.triangulos_degenerados() == 0


def test_trio_glb_un_nodo_por_pieza(trio):
    gltf = leer_glb(trio / "trio.glb")
    nodos = {n["name"]: n for n in gltf["nodes"]}
    piezas = {n for n in nodos if n in ("azul", "blanco", "rojo")}
    assert piezas == {"azul", "blanco", "rojo"}
    assert sum(1 for n in gltf["nodes"] if "mesh" in n) == 3
    raiz = nodos["bloques3d"]
    assert raiz["scale"] == pytest.approx([0.001] * 3)      # mm -> m (la unidad de glTF)
    assert {gltf["nodes"][i]["name"] for i in raiz["children"]} == {"azul", "blanco", "rojo"}
    nombres_mat = {m["name"] for m in gltf["materials"]}
    assert {"ABS_azul", "ABS_blanco", "ABS_rojo"} <= nombres_mat
    # blanco apoya en el azul: su nodo esta 9.6 mm mas arriba (Y es arriba en glTF)
    assert nodos["blanco"]["translation"][1] == pytest.approx(9.6, abs=1e-4)
    assert nodos["azul"].get("translation", [0, 0, 0])[1] == pytest.approx(0.0, abs=1e-6)


# --- Otras escenas, motores y video ---------------------------------------------------------

def test_casita_valida_en_blender(blender, tmp_path):
    cli("render", "escenas/casita.json", "--sin-render", "--salida", tmp_path, "--blender", blender)
    informe = comprobar(tmp_path / "casita.blend", "--blender", blender)
    assert informe["ok"], informe["fallos"]
    assert len(informe["contactos"]) >= 50
    assert all(c["pares_1um"] == 0 and c["vertices_enterrados"] == 0 for c in informe["contactos"])


def test_cycles_tambien_renderiza(blender, tmp_path):
    cli("render", "escenas/trio.json", "--motor", "cycles", "--res", "160x90", "--muestras", "4",
        "--salida", tmp_path, "--blender", blender)
    assert tamano_png(tmp_path / "trio.png") == (160, 90)


def test_video_giratorio_de_24_fotogramas(blender, tmp_path):
    cli("render", "escenas/trio.json", "--sin-render", "--res", "320x180", "--muestras", "4",
        "--turntable", "24", "--salida", tmp_path, "--blender", blender)
    mp4 = tmp_path / "trio_giro.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 1000
    datos = en_blender(blender, AQUI / "inspeccionar_video.py", mp4)
    assert datos["fotogramas"] == 24
    assert datos["tamano"] == [320, 180]


def test_escena_invalida_no_llega_a_blender(tmp_path):
    mala = tmp_path / "mala.json"
    mala.write_text(json.dumps({"piezas": [
        {"id": "a", "pieza": "ladrillo_2x4", "color": "azul", "pos": [0, 0]},
        {"id": "b", "pieza": "ladrillo_2x4", "color": "rojo", "pos": [1, 0]}]}), encoding="utf-8")
    proc = cli("render", mala, "--salida", tmp_path, esperado=2)
    assert "'b' se solapa con 'a'" in proc.stderr
    assert not (tmp_path / "mala.blend").exists()
