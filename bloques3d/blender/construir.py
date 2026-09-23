"""Script de entrada para Blender: construye, guarda, renderiza y exporta una escena.

Normalmente lo lanza ``python -m bloques3d render ...``, pero tambien se puede
usar a mano::

    blender --background --factory-startup --python bloques3d/blender/construir.py -- \\
        --escena escenas/trio.json --res 1280x720 --muestras 32

La ultima linea que imprime empieza por ``BLOQUES3D_RESULTADO`` y lleva un
JSON con las rutas generadas y los tiempos.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from bloques3d import __version__  # noqa: E402
from bloques3d.encuadre import distancia_orbita, encuadrar  # noqa: E402
from bloques3d.escena import Escena, EscenaInvalida, cargar_escena  # noqa: E402
from bloques3d.opciones import anadir_opciones_render  # noqa: E402
from bloques3d.paleta import PALETA  # noqa: E402
from bloques3d.blender import estudio, exportar, malla  # noqa: E402

MARCA = "BLOQUES3D_RESULTADO"


def log(msg: str) -> None:
    print(f"[bloques3d] {msg}", flush=True)


def construir_escena(escena: Escena, aspecto: float):
    """Crea piezas, camara, estudio y luces. Devuelve (objetos, camara, encuadre)."""
    scene = bpy.context.scene
    estudio.vaciar_escena()
    estudio.configurar_unidades(scene)

    col_piezas = bpy.data.collections.new("Piezas")
    col_estudio = bpy.data.collections.new("Estudio")
    scene.collection.children.link(col_piezas)
    scene.collection.children.link(col_estudio)

    objetos = []
    for c in escena.piezas:
        obj = malla.crear_objeto(c.pieza, c.id, col_piezas)
        obj.location = c.centro_mm
        obj.rotation_euler = (0.0, 0.0, math.radians(c.giro_grados))
        # Las piezas del mismo tipo comparten malla; el color va en el objeto.
        if not obj.data.materials:
            obj.data.materials.append(None)
        ranura = obj.material_slots[0]
        ranura.link = "OBJECT"
        ranura.material = estudio.material_abs(PALETA[c.color])
        obj["bloques3d_color"] = c.color
        obj["bloques3d_pos"] = [c.x, c.y]
        obj["bloques3d_nivel"] = c.nivel
        obj["bloques3d_suelta"] = c.suelta
        objetos.append(obj)

    cfg = escena.camara
    enc = encuadrar(escena.puntos(), cfg.azimut, cfg.elevacion, cfg.lente, aspecto, cfg.margen)
    if cfg.enfoque is not None:
        foco = escena.por_id(cfg.enfoque)
        cx, cy, _ = foco.centro_mm
        punto_foco = (cx, cy, (foco.z_min + foco.z_max) / 2)
    else:
        (x0, y0, z0), (x1, y1, z1) = escena.caja()
        punto_foco = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    cam = estudio.camara(enc, col_estudio, cfg.apertura, enc.camara_local(punto_foco)[2])

    (x0, y0, _), (x1, y1, z1) = escena.caja()
    centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, z1 / 3))
    radio = max(Vector((x1 - x0, y1 - y0, z1)).length / 2, 12.0)
    # El cuenco del fondo tiene que dejar dentro la camara fija, la orbita
    # del video giratorio y las luces (a <= 7 radios).
    cam_h = (Vector(enc.posicion) - centro).to_2d().length
    orbita_h = distancia_orbita(escena.puntos(), tuple(centro), cfg.elevacion, cfg.lente, aspecto,
                                cfg.margen, muestras=72) * math.cos(math.radians(cfg.elevacion))
    radio_suelo = max(8.0 * radio, 1.25 * cam_h, 1.25 * orbita_h)
    estudio.ciclorama(Vector((centro.x, centro.y, 0)), radio_suelo, 3.0 * radio, escena.fondo, col_estudio)
    estudio.luces_tres_puntos(centro, radio, cfg.azimut, col_estudio)
    estudio.mundo(escena.fondo)
    return objetos, cam, enc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="construir.py")
    ap.add_argument("--escena", required=True)
    anadir_opciones_render(ap)
    args = ap.parse_args(argv)

    t0 = time.perf_counter()
    try:
        escena = cargar_escena(args.escena)
    except EscenaInvalida as e:
        print(str(e), file=sys.stderr, flush=True)
        return 2
    log(escena.resumen())

    ancho, alto = args.res
    scene = bpy.context.scene
    estudio.configurar_render(scene, args.motor, ancho, alto, args.muestras)
    objetos, cam, enc = construir_escena(escena, ancho / alto)
    tiempos = {"construir": round(time.perf_counter() - t0, 2)}

    salida = Path(args.salida).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    resultado: dict = {
        "version": __version__,
        "escena": escena.nombre,
        "piezas": len(escena.piezas),
        "motor": args.motor,
        "resolucion": [ancho, alto],
        "muestras": args.muestras,
        "camara": {"posicion": [round(v, 3) for v in enc.posicion], "lente": enc.lente},
    }

    # El render se guarda junto al .blend con ruta relativa ("//"), asi el
    # archivo funciona en cualquier PC.
    blend = salida / f"{escena.nombre}.blend"
    scene.render.filepath = f"//{escena.nombre}.png"
    estudio.configurar_salida_imagen(scene, "PNG")
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True, relative_remap=True)
    resultado["blend"] = str(blend)
    log(f"guardado {blend}")

    if not args.sin_render:
        t = time.perf_counter()
        png = salida / f"{escena.nombre}.png"
        scene.render.filepath = str(png)
        bpy.ops.render.render(write_still=True)
        tiempos["render"] = round(time.perf_counter() - t, 2)
        resultado["png"] = str(png)
        log(f"render {ancho}x{alto} ({args.motor}, {args.muestras} muestras) en {tiempos['render']} s -> {png}")
        if args.jpeg:
            jpg = salida / f"{escena.nombre}.jpg"
            estudio.configurar_salida_imagen(scene, "JPEG")
            bpy.data.images["Render Result"].save_render(filepath=str(jpg), scene=scene)
            estudio.configurar_salida_imagen(scene, "PNG")
            resultado["jpg"] = str(jpg)
            log(f"copia JPEG -> {jpg}")
        scene.render.filepath = f"//{escena.nombre}.png"

    if args.stl:
        t = time.perf_counter()
        piezas = sorted({c.pieza for c in escena.piezas}, key=lambda p: p.clave)
        resultado["stl"] = exportar.exportar_stl(piezas, Path(args.stl).resolve())
        tiempos["stl"] = round(time.perf_counter() - t, 2)
        log(f"{len(resultado['stl'])} STL -> {Path(args.stl).resolve()}")

    if args.glb:
        t = time.perf_counter()
        resultado["glb"] = exportar.exportar_glb(objetos, Path(args.glb).resolve())
        tiempos["glb"] = round(time.perf_counter() - t, 2)
        log(f"GLB -> {resultado['glb']}")

    if args.turntable:
        t = time.perf_counter()
        cfg = escena.camara
        (x0, y0, z0), (x1, y1, z1) = escena.caja()
        centro = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        dist = distancia_orbita(escena.puntos(), tuple(centro), cfg.elevacion, cfg.lente,
                                ancho / alto, cfg.margen)
        exportar.preparar_giro(scene, cam, centro, dist, cfg.azimut, cfg.elevacion, args.turntable)
        mp4 = exportar.render_giro(scene, salida / f"{escena.nombre}_giro.mp4")
        tiempos["turntable"] = round(time.perf_counter() - t, 2)
        resultado["mp4"] = mp4
        resultado["fotogramas"] = args.turntable
        log(f"vídeo de {args.turntable} fotogramas en {tiempos['turntable']} s -> {mp4}")

    tiempos["total"] = round(time.perf_counter() - t0, 2)
    resultado["tiempos"] = tiempos
    print(MARCA + " " + json.dumps(resultado, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sys.exit(main(argv))
