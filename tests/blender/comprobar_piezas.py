"""Se ejecuta DENTRO de Blender (lo lanza test_blender.py).

Construye cada pieza del catalogo y varios apilados, y devuelve un JSON con
las medidas reales de las mallas evaluadas y el informe de interpenetracion.
"""
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

import bmesh  # noqa: E402
import bpy  # noqa: E402

from bloques3d.blender import malla  # noqa: E402
from bloques3d.blender.comprobar import comprobar  # noqa: E402
from bloques3d.escena import escena_desde_dict  # noqa: E402
from bloques3d.medidas import CATALOGO, plan_pieza  # noqa: E402


def limpiar():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def medir(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    no_manifold = sum(1 for e in bm.edges if not e.is_manifold)
    cos = [v.co.copy() for v in bm.verts]
    bm.free()
    ev.to_mesh_clear()
    lo = [min(c[i] for c in cos) for i in range(3)]
    hi = [max(c[i] for c in cos) for i in range(3)]
    (x0, y0, z0), (x1, y1, z1) = plan_pieza_de(obj).caja
    fuera = max(max(x0 - c.x, c.x - x1, y0 - c.y, c.y - y1, z0 - c.z, c.z - z1, 0.0) for c in cos)
    return {
        "dim": [round(hi[i] - lo[i], 5) for i in range(3)],
        "z_min": round(lo[2], 6),
        "no_manifold_base": malla.aristas_no_manifold(obj.data),
        "no_manifold_evaluada": no_manifold,
        "fuera_de_la_caja": round(fuera, 6),
        "vertices": len(cos),
    }


def plan_pieza_de(obj):
    return plan_pieza(CATALOGO.get(obj["bloques3d_pieza"]) or _pieza(obj["bloques3d_pieza"]))


def _pieza(clave):
    from bloques3d.medidas import pieza_por_clave
    return pieza_por_clave(clave)


resultado = {"piezas": {}, "apilados": {}}
for clave, pieza in CATALOGO.items():
    limpiar()
    resultado["piezas"][clave] = medir(malla.crear_objeto(pieza, clave))

# Apilados reales, colocados con el mismo codigo de escenas que usa construir.py
APILADOS = {
    "2x4_sobre_2x4_desplazado_2_studs": [("ladrillo_2x4", [0, 0], 0, 0), ("ladrillo_2x4", [2, 0], 3, 0)],
    "2x4_sobre_2x4_como_trio": [("ladrillo_2x4", [0, 0], 0, 0), ("ladrillo_2x4", [-2, 1], 3, 0)],
    "2x4_girado_sobre_2x4": [("ladrillo_2x4", [0, 0], 0, 0), ("ladrillo_2x4", [1, -1], 3, 90)],
    "1x4_sobre_1x4_desplazado": [("ladrillo_1x4", [0, 0], 0, 0), ("ladrillo_1x4", [1, 0], 3, 0)],
    "1x4_sobre_1x1": [("ladrillo_1x1", [2, 0], 0, 0), ("ladrillo_1x4", [0, 0], 3, 0)],
    "placa_4x4_sobre_2x2": [("ladrillo_2x2", [1, 1], 0, 0), ("placa_4x4", [0, 0], 3, 0)],
    "baldosa_sobre_placa": [("placa_2x4", [0, 0], 0, 0), ("baldosa_2x2", [1, 0], 1, 0)],
    "2x6_sobre_dos_2x2": [("ladrillo_2x2", [0, 0], 0, 0), ("ladrillo_2x2", [4, 0], 0, 0),
                          ("ladrillo_2x6", [0, 0], 3, 0)],
}
for nombre, piezas in APILADOS.items():
    limpiar()
    escena = escena_desde_dict({"piezas": [
        {"id": f"p{i}", "pieza": clave, "color": "azul", "pos": pos, "nivel": nivel, "rot": rot}
        for i, (clave, pos, nivel, rot) in enumerate(piezas)
    ]})
    objs = []
    for c in escena.piezas:
        o = malla.crear_objeto(c.pieza, c.id)
        o.location = c.centro_mm
        o.rotation_euler = (0, 0, math.radians(c.giro_grados))
        o["bloques3d_nivel"] = c.nivel
        objs.append(o)
    bpy.context.view_layer.update()
    informe = comprobar(objs, [o for o in objs if o["bloques3d_nivel"] == 0], None)
    resultado["apilados"][nombre] = {
        "ok": informe["ok"], "fallos": informe["fallos"], "contactos": informe["contactos"],
        "conexiones_escena": len(escena.conexiones()),
    }

print("RESULTADO_PRUEBA " + json.dumps(resultado), flush=True)
