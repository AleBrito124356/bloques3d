import argparse
import json
from pathlib import Path

import pytest

from bloques3d import cli
from bloques3d.opciones import resolucion

RAIZ = Path(__file__).resolve().parents[1]


def exe_falso(ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(b"")
    return ruta


def test_blender_por_variable_de_entorno(tmp_path):
    exe = exe_falso(tmp_path / "mi_blender.exe")
    assert cli.buscar_blender(entorno={"BLENDER_EXE": str(exe), "PATH": str(tmp_path / "vacio")}) == exe


def test_blender_explicito_manda(tmp_path):
    exe = exe_falso(tmp_path / "b.exe")
    assert cli.buscar_blender(str(exe), entorno={"BLENDER_EXE": "no/existe"}) == exe


def test_blender_env_roto_es_un_error_claro(tmp_path):
    with pytest.raises(cli.BlenderNoEncontrado, match="BLENDER_EXE apunta a"):
        cli.buscar_blender(entorno={"BLENDER_EXE": str(tmp_path / "nada.exe")})


def test_blender_no_encontrado(tmp_path):
    with pytest.raises(cli.BlenderNoEncontrado, match="BLENDER_EXE"):
        cli.buscar_blender(entorno={"PATH": str(tmp_path)}, sistema="Plan9")


def test_windows_elige_la_version_mas_nueva(tmp_path):
    base = tmp_path / "Program Files"
    for v in ("4.2", "5.2", "10.0", "9.1"):
        exe_falso(base / "Blender Foundation" / f"Blender {v}" / "blender.exe")
    entorno = {"ProgramFiles": str(base), "PATH": str(tmp_path / "vacio")}
    candidatos = [c for c in cli.candidatos_blender(entorno, "Windows") if c.startswith(str(base))]
    assert [Path(c).parent.name for c in candidatos] == ["Blender 10.0", "Blender 9.1", "Blender 5.2", "Blender 4.2"]
    assert cli.buscar_blender(entorno=entorno, sistema="Windows").parent.name == "Blender 10.0"


def args_render(**kw):
    base = dict(res=(640, 360), muestras=16, motor="eevee", salida="salida", jpeg=False, sin_render=False)
    return argparse.Namespace(**{**base, **kw})


def test_comando_siempre_sin_interfaz_y_de_fabrica(tmp_path):
    cmd = cli.comando_blender(Path("blender"), tmp_path / "e.json",
                              args_render(jpeg=True, motor="cycles"))
    assert cmd[1:3] == ["--background", "--factory-startup"]
    assert cmd[cmd.index("--python") + 1] == str(cli.SCRIPT_BLENDER)
    tras = cmd[cmd.index("--") + 1:]
    assert tras[tras.index("--res") + 1] == "640x360"
    assert tras[tras.index("--motor") + 1] == "cycles"
    assert "--jpeg" in tras
    assert Path(tras[tras.index("--salida") + 1]).is_absolute()


@pytest.mark.parametrize("texto, esperado", [("1920x1080", (1920, 1080)), (" 640X360 ", (640, 360))])
def test_resolucion(texto, esperado):
    assert resolucion(texto) == esperado


@pytest.mark.parametrize("texto", ["1920", "0x0", "abcxdef", "99999x10", ""])
def test_resolucion_invalida(texto):
    with pytest.raises(argparse.ArgumentTypeError):
        resolucion(texto)


def test_validar_escenas_incluidas(capsys):
    assert cli.main(["validar", str(RAIZ / "escenas" / "trio.json"), str(RAIZ / "escenas" / "casita.json")]) == 0
    salida = capsys.readouterr().out
    assert salida.count("OK ") == 2


def test_validar_escena_rota(tmp_path, capsys):
    ruta = tmp_path / "mala.json"
    ruta.write_text(json.dumps({"piezas": [
        {"id": "a", "pieza": "ladrillo_2x2", "color": "rojo", "pos": [0, 0]},
        {"id": "b", "pieza": "ladrillo_2x2", "color": "rojo", "pos": [9, 9], "nivel": 3}]}), encoding="utf-8")
    assert cli.main(["validar", str(ruta)]) == 1
    assert "'b' (nivel 3) está flotando" in capsys.readouterr().out


def test_catalogo_json(capsys):
    assert cli.main(["catalogo", "--json"]) == 0
    filas = {f["clave"]: f for f in json.loads(capsys.readouterr().out)}
    assert filas["ladrillo_2x4"]["medidas_mm"] == [31.8, 15.8, 11.3]
    assert filas["ladrillo_2x4"]["n_tubos"] == 3


def test_render_escena_invalida_no_lanza_blender(tmp_path, monkeypatch, capsys):
    ruta = tmp_path / "mala.json"
    ruta.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: pytest.fail("no debia lanzar Blender"))
    assert cli.main(["render", str(ruta)]) == 2
    assert "no es válida" in capsys.readouterr().err


class ProcesoFalso:
    def __init__(self, lineas, codigo=0):
        self.stdout = iter(l + "\n" for l in lineas)
        self.codigo = codigo

    def wait(self):
        return self.codigo


def test_render_lee_el_resultado_de_blender(tmp_path, monkeypatch, capsys):
    exe = exe_falso(tmp_path / "blender.exe")
    visto = {}
    resultado = {"blend": str(tmp_path / "trio.blend"), "png": str(tmp_path / "trio.png"),
                 "tiempos": {"render": 1.5, "total": 2.0}}

    def popen(cmd, **kw):
        visto["cmd"] = cmd
        return ProcesoFalso(["Fra:1 ruido de Blender", "[bloques3d] construyendo",
                             cli.MARCA + " " + json.dumps(resultado)])

    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    rc = cli.main(["render", str(RAIZ / "escenas" / "trio.json"), "--blender", str(exe), "--res", "320x180"])
    out = capsys.readouterr().out
    assert rc == 0
    assert visto["cmd"][:3] == [str(exe), "--background", "--factory-startup"]
    assert "[bloques3d] construyendo" in out and "Fra:1" not in out
    assert "trio.png" in out and "trio.blend" in out and "render 1.5" in out


def test_render_error_de_blender_muestra_la_cola(tmp_path, monkeypatch, capsys):
    exe = exe_falso(tmp_path / "blender.exe")
    monkeypatch.setattr(cli.subprocess, "Popen",
                        lambda cmd, **kw: ProcesoFalso(["Traceback...", "RuntimeError: algo"], codigo=1))
    rc = cli.main(["render", str(RAIZ / "escenas" / "trio.json"), "--blender", str(exe)])
    assert rc == 1
    assert "RuntimeError: algo" in capsys.readouterr().err
