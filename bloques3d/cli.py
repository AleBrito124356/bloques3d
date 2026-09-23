"""Linea de comandos: ``python -m bloques3d {render,validar,comprobar,catalogo,blender}``.

La CLI es Python puro. Para renderizar busca Blender y lo lanza siempre con
``--background --factory-startup`` (sin ventana y sin tocar las preferencias
ni los add-ons del usuario).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path

from . import __version__
from .escena import EscenaInvalida, cargar_escena
from .medidas import CATALOGO, plan_pieza
from .opciones import anadir_opciones_render

SCRIPT_BLENDER = Path(__file__).resolve().parent / "blender" / "construir.py"
SCRIPT_COMPROBAR = Path(__file__).resolve().parent / "blender" / "comprobar.py"
MARCA = "BLOQUES3D_RESULTADO"
MARCA_COMPROBACION = "BLOQUES3D_COMPROBACION"
ARGS_SEGUROS = ("--background", "--factory-startup")


class BlenderNoEncontrado(RuntimeError):
    pass


def _clave_version(ruta: str) -> tuple[int, ...]:
    m = re.search(r"Blender[ _-]?(\d+(?:\.\d+)*)", ruta)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def candidatos_blender(entorno: dict | None = None, sistema: str | None = None) -> list[str]:
    """Rutas donde buscar Blender, en orden de preferencia."""
    entorno = os.environ if entorno is None else entorno
    sistema = sistema or platform.system()
    out: list[str] = []
    if entorno.get("BLENDER_EXE"):
        out.append(entorno["BLENDER_EXE"])
    en_path = shutil.which("blender", path=entorno.get("PATH"))
    if en_path:
        out.append(en_path)
    if sistema == "Windows":
        bases = [entorno.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files"]
        encontrados: list[str] = []
        for base in dict.fromkeys(bases):
            encontrados += glob.glob(os.path.join(base, "Blender Foundation", "Blender*", "blender.exe"))
        out += sorted(set(encontrados), key=_clave_version, reverse=True)
    elif sistema == "Darwin":
        out.append("/Applications/Blender.app/Contents/MacOS/Blender")
    else:
        out += ["/usr/bin/blender", "/usr/local/bin/blender", "/snap/bin/blender"]
    return list(dict.fromkeys(out))


def buscar_blender(explicito: str | None = None, entorno: dict | None = None,
                   sistema: str | None = None) -> Path:
    """Devuelve el ejecutable de Blender o lanza :class:`BlenderNoEncontrado`.

    Orden: ``--blender``, variable ``BLENDER_EXE``, ``blender`` en el PATH y
    la instalacion estandar del sistema (en Windows, la version mas nueva de
    ``Program Files/Blender Foundation``).
    """
    if explicito:
        p = Path(explicito)
        if p.is_file():
            return p
        raise BlenderNoEncontrado(f"--blender apunta a {explicito}, que no existe")
    entorno = os.environ if entorno is None else entorno
    if entorno.get("BLENDER_EXE") and not Path(entorno["BLENDER_EXE"]).is_file():
        raise BlenderNoEncontrado(f"BLENDER_EXE apunta a {entorno['BLENDER_EXE']}, que no existe")
    for c in candidatos_blender(entorno, sistema):
        if Path(c).is_file():
            return Path(c)
    raise BlenderNoEncontrado(
        "no encuentro Blender. Instálalo (blender.org, 5.0 o superior; probado con 5.2.1) o indica "
        "la ruta con --blender RUTA o con la variable de entorno BLENDER_EXE"
    )


def comando_blender(exe: Path, escena: Path, args: argparse.Namespace) -> list[str]:
    """Linea de comandos completa para ``construir.py``."""
    ancho, alto = args.res
    cmd = [str(exe), *ARGS_SEGUROS, "--python-exit-code", "1", "--python", str(SCRIPT_BLENDER), "--",
           "--escena", str(escena), "--salida", str(Path(args.salida).resolve()),
           "--res", f"{ancho}x{alto}", "--muestras", str(args.muestras), "--motor", args.motor]
    if args.jpeg:
        cmd.append("--jpeg")
    if args.sin_render:
        cmd.append("--sin-render")
    if args.stl:
        cmd += ["--stl", str(Path(args.stl).resolve())]
    if args.glb:
        cmd += ["--glb", str(Path(args.glb).resolve())]
    if args.turntable:
        cmd += ["--turntable", str(args.turntable)]
    return cmd


def _relativa(ruta: str) -> str:
    """Ruta relativa al directorio actual si cuelga de el; si no, la original."""
    try:
        rel = os.path.relpath(ruta)
    except ValueError:  # otra unidad en Windows
        return ruta
    return ruta if rel.startswith("..") else rel


def cmd_render(args: argparse.Namespace) -> int:
    escena_path = Path(args.escena)
    try:
        escena = cargar_escena(escena_path)
    except EscenaInvalida as e:
        print(str(e), file=sys.stderr)
        return 2
    try:
        exe = buscar_blender(args.blender)
    except BlenderNoEncontrado as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    print(f"escena  {escena.resumen()}")
    print(f"blender {exe}")
    cmd = comando_blender(exe, escena_path.resolve(), args)
    ultimas: deque[str] = deque(maxlen=40)
    resultado = None
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace")
    assert proc.stdout is not None
    for linea in proc.stdout:
        linea = linea.rstrip("\n")
        ultimas.append(linea)
        if linea.startswith(MARCA):
            resultado = json.loads(linea[len(MARCA):].strip())
        elif linea.startswith("[bloques3d]") or args.verboso:
            print(linea, flush=True)
    codigo = proc.wait()
    if codigo != 0 or resultado is None:
        print(f"error: Blender terminó con código {codigo}. Últimas líneas:", file=sys.stderr)
        for linea in ultimas:
            print(f"  | {linea}", file=sys.stderr)
        return codigo or 1
    print("archivos:")
    for clave in ("blend", "png", "jpg", "glb", "mp4"):
        if clave in resultado:
            print(f"  {clave:5} {_relativa(resultado[clave])}")
    for stl in resultado.get("stl", []):
        print(f"  stl   {_relativa(stl)}")
    print("tiempos (s): " + ", ".join(f"{k} {v}" for k, v in resultado["tiempos"].items()))
    return 0


def comando_comprobar(exe: Path, blend: Path, args: argparse.Namespace) -> list[str]:
    cmd = [str(exe), *ARGS_SEGUROS, str(blend), "--python-exit-code", "2", "--python", str(SCRIPT_COMPROBAR),
           "--", "--margen", str(args.margen)]
    if args.piezas:
        cmd += ["--piezas", args.piezas]
    if args.suelo:
        cmd += ["--suelo", args.suelo]
    return cmd


def cmd_comprobar(args: argparse.Namespace) -> int:
    blend = Path(args.blend)
    if not blend.is_file():
        print(f"error: no existe {blend}", file=sys.stderr)
        return 2
    try:
        exe = buscar_blender(args.blender)
    except BlenderNoEncontrado as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    proc = subprocess.run(comando_comprobar(exe, blend.resolve(), args), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=1800)
    linea = next((l for l in proc.stdout.splitlines() if l.startswith(MARCA_COMPROBACION)), None)
    if linea is None:
        print(f"error: la comprobación no terminó (código {proc.returncode}):", file=sys.stderr)
        for l in (proc.stdout + proc.stderr).splitlines()[-30:]:
            print(f"  | {l}", file=sys.stderr)
        return 2
    informe = json.loads(linea[len(MARCA_COMPROBACION):].strip())
    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
    else:
        enc = informe.get("encuadre")
        if enc:
            print(f"encuadre   u {enc['u'][0]:.3f}..{enc['u'][1]:.3f}   v {enc['v'][0]:.3f}..{enc['v'][1]:.3f}"
                  f"   (margen exigido {enc['margen']})")
        print(f"suelo      {len(informe['suelo'])} piezas con z mínima = "
              + ", ".join(f"{v:g}" for v in informe["suelo"].values()))
        cont = informe["contactos"]
        print(f"contactos  {len(cont)} pares de piezas que se tocan; con 1 micra de separación se cruzan "
              f"{sum(c['pares_1um'] for c in cont)} pares de caras; vértices enterrados: "
              f"{sum(c['vertices_enterrados'] for c in cont)}")
        print(f"manifold   {sum(informe['aristas_no_manifold'].values())} aristas abiertas en "
              f"{len(informe['aristas_no_manifold'])} mallas")
        for f in informe["fallos"]:
            print(f"FALLO      {f}")
        print("OK" if informe["ok"] else f"{len(informe['fallos'])} fallo(s)")
    return 0 if informe["ok"] else 1


def cmd_validar(args: argparse.Namespace) -> int:
    fallos = 0
    for ruta in args.escenas:
        try:
            escena = cargar_escena(ruta)
        except EscenaInvalida as e:
            fallos += 1
            print(f"MAL {e}")
            continue
        print(f"OK  {ruta}: {escena.resumen()}")
    return 1 if fallos else 0


def filas_catalogo() -> list[dict]:
    filas = []
    for clave, pieza in CATALOGO.items():
        plan = plan_pieza(pieza)
        lx, ly, _ = plan.exterior
        filas.append({
            "clave": clave,
            "tipo": pieza.tipo,
            "studs": f"{pieza.ancho}x{pieza.largo}",
            "medidas_mm": [lx, ly, plan.altura_total],
            "altura_cuerpo_mm": pieza.altura,
            "n_studs": len(plan.studs),
            "n_tubos": len(plan.tubos),
            "n_barras": len(plan.barras),
        })
    return filas


def cmd_catalogo(args: argparse.Namespace) -> int:
    filas = filas_catalogo()
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2))
        return 0
    print(f"{'clave':14} {'tipo':9} {'medidas (mm, con studs)':25} {'studs':>5} {'tubos':>5} {'barras':>6}")
    for f in filas:
        lx, ly, lz = f["medidas_mm"]
        medidas = f"{lx:g} x {ly:g} x {lz:g}"
        print(f"{f['clave']:14} {f['tipo']:9} {medidas:25} {f['n_studs']:>5} {f['n_tubos']:>5} {f['n_barras']:>6}")
    print("\nCualquier tamaño se puede pedir en una escena con tipo_AxB, p. ej. placa_6x8 o ladrillo_1x3.")
    return 0


def cmd_blender(args: argparse.Namespace) -> int:
    try:
        exe = buscar_blender(args.blender)
    except BlenderNoEncontrado as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    salida = subprocess.run([str(exe), *ARGS_SEGUROS, "--version"], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=120)
    version = next((l for l in salida.stdout.splitlines() if l.startswith("Blender")), "¿versión?")
    print(f"{exe}\n{version}")
    return 0


def crear_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bloques3d",
        description="Piezas tipo LEGO paramétricas, escenas JSON y render en Blender sin interfaz.",
    )
    p.add_argument("--version", action="version", version=f"bloques3d {__version__}")
    sub = p.add_subparsers(dest="orden", required=True)

    r = sub.add_parser("render", help="construir una escena en Blender, guardar el .blend y renderizar")
    r.add_argument("escena", help="archivo JSON de la escena (p. ej. escenas/trio.json)")
    anadir_opciones_render(r)
    r.add_argument("--blender", help="ruta a blender(.exe); si no, BLENDER_EXE, PATH o instalación estándar")
    r.add_argument("-v", "--verboso", action="store_true", help="mostrar toda la salida de Blender")
    r.set_defaults(func=cmd_render)

    v = sub.add_parser("validar", help="comprobar escenas (colisiones y soporte) sin abrir Blender")
    v.add_argument("escenas", nargs="+")
    v.set_defaults(func=cmd_validar)

    c = sub.add_parser("catalogo", help="listar las piezas de serie con sus medidas")
    c.add_argument("--json", action="store_true")
    c.set_defaults(func=cmd_catalogo)

    k = sub.add_parser("comprobar", help="comprobar en Blender un .blend construido: encuadre, suelo, "
                                         "interpenetración y mallas cerradas")
    k.add_argument("blend")
    k.add_argument("--margen", type=float, default=0.03, help="margen mínimo del encuadre (0.03 = 3 %%)")
    k.add_argument("--piezas", help="objetos a comprobar, separados por comas (por defecto, colección Piezas)")
    k.add_argument("--suelo", help="objetos que deben apoyar en z=0 (por defecto, los de nivel 0)")
    k.add_argument("--json", action="store_true", help="imprimir el informe completo en JSON")
    k.add_argument("--blender")
    k.set_defaults(func=cmd_comprobar)

    b = sub.add_parser("blender", help="mostrar qué Blender se usaría")
    b.add_argument("--blender")
    b.set_defaults(func=cmd_blender)
    return p


def _salida_utf8() -> None:
    """En Windows, al redirigir la salida Python usa cp1252 y las tildes
    llegan rotas a Git Bash o a un archivo. Si el usuario no eligio otra
    codificacion (PYTHONIOENCODING), se fuerza UTF-8."""
    if os.environ.get("PYTHONIOENCODING"):
        return
    for flujo in (sys.stdout, sys.stderr):
        if (getattr(flujo, "encoding", "") or "").lower().replace("-", "") != "utf8" and hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _salida_utf8()
    args = crear_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
