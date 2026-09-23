"""Comprobaciones geometricas de un .blend ya construido (se ejecuta en Blender).

Uso (lo lanza ``python -m bloques3d comprobar salida/trio.blend``)::

    blender --background --factory-startup salida/trio.blend \\
        --python bloques3d/blender/comprobar.py -- [--margen 0.03] [--piezas A,B] [--suelo A,B]

Comprueba, sobre la malla **evaluada** (con el bisel):

* **encuadre**: todos los vertices de todas las piezas caen dentro de
  ``[margen, 1 - margen]`` en la imagen de la camara activa;
* **suelo**: las piezas de nivel 0 tienen su punto mas bajo en ``z = 0`` y
  ninguna pieza baja de ``z = 0``;
* **interpenetracion**: para cada par de piezas cuyas cajas se tocan,
  ``BVHTree.overlap`` con la de arriba elevada 1 micra no encuentra ningun
  par de caras, y ningun vertice de una esta dentro del solido de la otra
  (paridad de rayos). En contacto exacto las caras apoyadas se tocan en el
  plano de apoyo; eso no es interpenetracion y se informa aparte;
* **manifold**: cada malla de pieza es cerrada.

La prueba de "dentro del solido" (paridad de rayos por mayoria de 3
direcciones) es exacta para mallas que son una sola superficie cerrada, como
las de bloques3d. En mallas hechas uniendo cascarones que se solapan (el
.blend original de ``historial/``, con los studs como cilindros sueltos
metidos en la caja) el recuento es aproximado; el fallo se detecta igual.

Imprime ``BLOQUES3D_COMPROBACION {json}`` y sale con codigo 1 si algo falla.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import bmesh  # noqa: E402
import bpy  # noqa: E402
from bpy_extras.object_utils import world_to_camera_view  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

MARCA = "BLOQUES3D_COMPROBACION"
ELEVACION_PRUEBA = 0.001   # 1 micra (la escena esta en mm)
TOL_DENTRO = 1e-3          # a menos de 1 micra de la superficie = "en contacto", no dentro
PASO_RAYO = 1e-3
_DIRECCIONES = tuple(Vector(d).normalized() for d in
                     ((0.3017, 0.4079, 0.8618), (-0.7211, 0.2113, 0.6597), (0.1932, -0.8813, -0.4312)))


def bmesh_mundo(obj, depsgraph, desplazamiento: Vector | None = None):
    bm = bmesh.new()
    bm.from_object(obj, depsgraph)
    m = obj.matrix_world.copy()
    if desplazamiento is not None:
        m = Matrix.Translation(desplazamiento) @ m
    bm.transform(m)
    return bm


def _paridad(arbol: BVHTree, p: Vector, direccion: Vector, limite: float) -> int | None:
    """Cortes del rayo con la malla; ``None`` si el punto esta en la superficie."""
    cortes, origen = 0, p.copy()
    for _ in range(10000):
        hit, _, _, d = arbol.ray_cast(origen, direccion, limite)
        if hit is None:
            break
        if cortes == 0 and d < TOL_DENTRO:
            return None
        cortes += 1
        # mathutils trabaja en float32: a ~100 mm del origen un paso de 1e-5
        # se redondea sobre la misma cara y el rayo la cuenta varias veces.
        # 1 micra es mucho mayor que ese error y mucho menor que cualquier
        # detalle de las piezas.
        origen = hit + direccion * PASO_RAYO
    return cortes


def _dentro(arbol: BVHTree, p: Vector, limite: float) -> bool:
    """Paridad de rayos por mayoria de 3 direcciones: impar = dentro.

    Un solo rayo puede rozar una arista de silueta y contar mal; con tres
    direcciones independientes eso no pasa a la vez.
    """
    # find_nearest tiene ~1e-4..1e-3 de holgura numerica con puntos que estan
    # exactamente sobre una cara (medido con los tubos apoyados en z = 9.6),
    # asi que "en la superficie" se decide con la misma tolerancia de 1 micra
    # que la prueba de elevacion, y tambien si el primer corte del rayo es
    # inmediato.
    _, _, _, dist = arbol.find_nearest(p)
    if dist is not None and dist < TOL_DENTRO:
        return False
    votos = 0
    for direccion in _DIRECCIONES:
        cortes = _paridad(arbol, p, direccion, limite)
        if cortes is None:
            return False
        votos += cortes % 2
    return votos >= 2


class Pieza:
    def __init__(self, obj, depsgraph):
        self.obj = obj
        self.nombre = obj.name
        self.bm = bmesh_mundo(obj, depsgraph)
        self.arbol = BVHTree.FromBMesh(self.bm)
        self.arbol_elevado = None
        self.depsgraph = depsgraph
        cos = [v.co for v in self.bm.verts]
        self.min = Vector((min(c.x for c in cos), min(c.y for c in cos), min(c.z for c in cos)))
        self.max = Vector((max(c.x for c in cos), max(c.y for c in cos), max(c.z for c in cos)))

    def elevado(self) -> BVHTree:
        if self.arbol_elevado is None:
            bm = bmesh_mundo(self.obj, self.depsgraph, Vector((0, 0, ELEVACION_PRUEBA)))
            self.arbol_elevado = BVHTree.FromBMesh(bm)
            bm.free()
        return self.arbol_elevado

    def enterrados_en(self, otra: "Pieza") -> int:
        limite = (otra.max - otra.min).length * 2 + 1
        n = 0
        for v in self.bm.verts:
            c = v.co
            if (otra.min.x - 1e-3 <= c.x <= otra.max.x + 1e-3 and otra.min.y - 1e-3 <= c.y <= otra.max.y + 1e-3
                    and otra.min.z - 1e-3 <= c.z <= otra.max.z + 1e-3) and _dentro(otra.arbol, c, limite):
                n += 1
        return n


def _cajas_se_tocan(a: Pieza, b: Pieza, tol: float = 0.01) -> bool:
    return all(a.min[i] - tol <= b.max[i] and b.min[i] - tol <= a.max[i] for i in range(3))


def comprobar(piezas_obj, suelo_obj, margen: float | None) -> dict:
    """Informe de comprobaciones. Con ``margen=None`` no se mira el encuadre."""
    scene = bpy.context.scene
    dg = bpy.context.evaluated_depsgraph_get()
    piezas = [Pieza(o, dg) for o in piezas_obj]
    informe: dict = {"piezas": len(piezas), "fallos": []}

    # Encuadre
    cam = scene.camera
    if margen is None:
        pass
    elif cam is None:
        informe["fallos"].append("la escena no tiene cámara activa")
    else:
        us, vs = [], []
        peor = None
        for p in piezas:
            for v in p.bm.verts:
                u, w, prof = world_to_camera_view(scene, cam, v.co)
                us.append(u)
                vs.append(w)
                fuera = max(margen - u, u - (1 - margen), margen - w, w - (1 - margen), 0)
                if prof <= 0:
                    fuera = 1.0
                if fuera > 0 and (peor is None or fuera > peor[0]):
                    peor = (fuera, p.nombre, round(u, 4), round(w, 4))
        informe["encuadre"] = {"u": [round(min(us), 4), round(max(us), 4)],
                               "v": [round(min(vs), 4), round(max(vs), 4)], "margen": margen}
        if peor:
            informe["fallos"].append(f"{peor[1]} se sale del encuadre (u={peor[2]}, v={peor[3]})")

    # Suelo. Las escenas de bloques3d estan en mm; otros .blend, en unidades.
    unidad = "mm" if abs(scene.unit_settings.scale_length - 0.001) < 1e-9 else "unidades"
    informe["unidad"] = unidad
    nombres_suelo = {o.name for o in suelo_obj}
    informe["suelo"] = {}
    for p in piezas:
        if p.nombre in nombres_suelo:
            informe["suelo"][p.nombre] = round(p.min.z, 5)
            if abs(p.min.z) > 1e-4:
                informe["fallos"].append(f"{p.nombre} debería apoyar en z=0 y su punto más bajo está en "
                                         f"z={p.min.z:.4f} {unidad}")
        if p.min.z < -1e-4:
            informe["fallos"].append(f"{p.nombre} atraviesa el suelo (z minima {p.min.z:.4f} {unidad})")

    # Interpenetracion entre vecinas
    contactos = []
    for i, a in enumerate(piezas):
        for b in piezas[i + 1:]:
            if not _cajas_se_tocan(a, b):
                continue
            abajo, arriba = (a, b) if a.min.z <= b.min.z else (b, a)
            exactos = len(abajo.arbol.overlap(arriba.arbol))
            elevados = len(abajo.arbol.overlap(arriba.elevado()))
            enterrados = abajo.enterrados_en(arriba) + arriba.enterrados_en(abajo)
            contactos.append({"abajo": abajo.nombre, "arriba": arriba.nombre, "pares_contacto": exactos,
                              "pares_1um": elevados, "vertices_enterrados": enterrados})
            if elevados or enterrados:
                informe["fallos"].append(
                    f"{arriba.nombre} atraviesa a {abajo.nombre}: {elevados} pares de caras con 1 micra "
                    f"de separación, {enterrados} vértices dentro del sólido de la otra")
    informe["contactos"] = contactos

    # Manifold (por malla, una sola vez)
    abiertas = {}
    for o in piezas_obj:
        if o.data.name in abiertas:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        abiertas[o.data.name] = sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
    informe["aristas_no_manifold"] = abiertas
    for nombre, n in abiertas.items():
        if n:
            informe["fallos"].append(f"la malla {nombre} tiene {n} aristas abiertas (no es cerrada)")

    for p in piezas:
        p.bm.free()
    informe["ok"] = not informe["fallos"]
    return informe


def _objetos(nombres: str | None, por_defecto):
    if nombres:
        faltan = [n for n in nombres.split(",") if n not in bpy.data.objects]
        if faltan:
            raise SystemExit(f"no existen los objetos: {', '.join(faltan)}")
        return [bpy.data.objects[n] for n in nombres.split(",")]
    return por_defecto


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="comprobar.py")
    ap.add_argument("--margen", type=float, default=0.03)
    ap.add_argument("--piezas", help="nombres de objeto separados por comas (por defecto: coleccion Piezas)")
    ap.add_argument("--suelo", help="piezas que deben apoyar en z=0 (por defecto: las de nivel 0)")
    args = ap.parse_args(argv)

    coleccion = bpy.data.collections.get("Piezas")
    defecto = [o for o in (coleccion.all_objects if coleccion else []) if o.type == "MESH"]
    piezas = _objetos(args.piezas, defecto)
    if not piezas:
        raise SystemExit("no hay piezas que comprobar (ni coleccion 'Piezas' ni --piezas)")
    suelo = _objetos(args.suelo, [o for o in piezas if o.get("bloques3d_nivel", -1) == 0])
    informe = comprobar(piezas, suelo, args.margen)
    informe["archivo"] = bpy.data.filepath
    print(MARCA + " " + json.dumps(informe, ensure_ascii=False), flush=True)
    return 0 if informe["ok"] else 1


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sys.exit(main(argv))
