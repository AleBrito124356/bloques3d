"""Construccion de la malla de cada pieza con ``bmesh`` (sin ``bpy.ops``).

Funciona en ``blender --background`` sin ventana ni contexto de operador.
La malla resultante es **una sola superficie cerrada y manifold**:

* cuerpo hueco: paredes exteriores, reborde inferior, paredes interiores
  y techo interior (grosor ``PARED`` y ``TECHO``);
* studs fusionados con la cara superior (la cara superior tiene un agujero
  por stud, rellenado con ``triangle_fill``);
* tubos huecos (piezas 2xN) y barras macizas (piezas 1xN) que bajan desde
  el techo interior hasta ``z = 0``.

El origen queda en el centro de la cara inferior, asi que ``z = 0`` es
"apoyada en el suelo".
"""
from __future__ import annotations

import math

import bmesh
import bpy

from ..medidas import PlanPieza, Pieza, plan_pieza

SEGMENTOS_STUD = 32
SEGMENTOS_TUBO = 32
SEGMENTOS_BARRA = 24
BISEL_MM = 0.15
BISEL_SEGMENTOS = 2
ANGULO_NITIDO = math.radians(30.0)
MARCO_MM = 0.6
CAPA_BISEL = "bevel_weight_edge"   # atributo que lee el modificador Bevel


def _circulo(bm, cx: float, cy: float, z: float, r: float, n: int) -> list:
    # Desfase de medio segmento: ningun vertice apunta exactamente hacia el
    # stud/tubo vecino (que es tangente por diseno), asi las piezas encajadas
    # no comparten ni un punto.
    paso = 2.0 * math.pi / n
    return [
        bm.verts.new((cx + r * math.cos((i + 0.5) * paso), cy + r * math.sin((i + 0.5) * paso), z))
        for i in range(n)
    ]


def _unir_anillos(bm, a: list, b: list) -> None:
    """Caras quad entre dos anillos de vertices del mismo tamano."""
    n = len(a)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))


def _aristas_de_anillo(bm, anillo: list) -> list:
    n = len(anillo)
    return [bm.edges.new((anillo[i], anillo[(i + 1) % n])) for i in range(n)]


def _rellenar(bm, contorno: list, huecos: list[list]) -> None:
    """Rellena un rectangulo plano (4 vertices, en sentido antihorario) con
    agujeros circulares.

    Primero se crea un marco de 4 quads (``MARCO_MM`` hacia dentro) y despues
    se rellena el rectangulo interior con ``triangle_fill``, que usa scanfill y
    trata los lazos interiores como agujeros. Sin el marco, alguna diagonal
    del relleno llega a una esquina de la pieza y el bisel saca un vertice
    ~0.013 mm fuera de la pared (medido en el 1x1).
    """
    z = contorno[0].co.z
    interior = [
        bm.verts.new((v.co.x - math.copysign(MARCO_MM, v.co.x), v.co.y - math.copysign(MARCO_MM, v.co.y), z))
        for v in contorno
    ]
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((contorno[i], contorno[j], interior[j], interior[i]))
    if not huecos:
        bm.faces.new(interior)
        return
    aristas = [bm.edges.get((interior[i], interior[(i + 1) % 4])) for i in range(4)]
    for anillo in huecos:
        aristas.extend(_aristas_de_anillo(bm, anillo))
    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=True, edges=aristas)


def construir_bmesh(plan: PlanPieza):
    """Devuelve un ``bmesh.types.BMesh`` con la pieza descrita por ``plan``."""
    bm = bmesh.new()
    lx, ly, h = plan.exterior
    cx, cy, _ = plan.cavidad
    zc = plan.cavidad[2]           # altura del techo interior

    def rect(ax: float, ay: float, z: float) -> list:
        return [
            bm.verts.new((-ax / 2, -ay / 2, z)),
            bm.verts.new((ax / 2, -ay / 2, z)),
            bm.verts.new((ax / 2, ay / 2, z)),
            bm.verts.new((-ax / 2, ay / 2, z)),
        ]

    arriba = rect(lx, ly, h)       # borde de la cara superior
    abajo = rect(lx, ly, 0.0)      # borde exterior inferior
    interior = rect(cx, cy, 0.0)   # borde interior inferior
    techo = rect(cx, cy, zc)       # techo de la cavidad

    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((abajo[i], abajo[j], arriba[j], arriba[i]))         # pared exterior
        bm.faces.new((abajo[i], interior[i], interior[j], abajo[j]))     # reborde inferior
        bm.faces.new((interior[i], techo[i], techo[j], interior[j]))     # pared interior

    # Cara superior + studs.
    bases = [_circulo(bm, x, y, h, plan.stud_radio, SEGMENTOS_STUD) for x, y in plan.studs]
    _rellenar(bm, arriba, bases)
    for base in bases:
        cima = [bm.verts.new((v.co.x, v.co.y, h + plan.stud_altura)) for v in base]
        _unir_anillos(bm, base, cima)
        bm.faces.new(cima)

    # Techo interior + tubos y barras.
    tubos_ext = [_circulo(bm, x, y, zc, plan.tubo_radio_ext, SEGMENTOS_TUBO) for x, y in plan.tubos]
    barras = [_circulo(bm, x, y, zc, plan.barra_radio, SEGMENTOS_BARRA) for x, y in plan.barras]
    _rellenar(bm, techo, tubos_ext + barras)

    for (x, y), ext_arriba in zip(plan.tubos, tubos_ext):
        ext_abajo = [bm.verts.new((v.co.x, v.co.y, 0.0)) for v in ext_arriba]
        int_abajo = _circulo(bm, x, y, 0.0, plan.tubo_radio_int, SEGMENTOS_TUBO)
        int_arriba = [bm.verts.new((v.co.x, v.co.y, zc)) for v in int_abajo]
        _unir_anillos(bm, ext_arriba, ext_abajo)    # pared exterior del tubo
        _unir_anillos(bm, ext_abajo, int_abajo)     # anillo inferior
        _unir_anillos(bm, int_abajo, int_arriba)    # pared interior del tubo
        bm.faces.new(int_arriba)                    # fondo del hueco del tubo

    for anillo in barras:
        pie = [bm.verts.new((v.co.x, v.co.y, 0.0)) for v in anillo]
        _unir_anillos(bm, anillo, pie)
        bm.faces.new(pie)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = True
    marcar_bisel(bm)
    return bm


def marcar_bisel(bm) -> None:
    """Peso de bisel 1 solo en las aristas **convexas** vivas.

    Las concavas (base de cada stud, union techo-tubo) se dejan vivas: un
    redondeo concavo en la base del stud anade material fuera de su cilindro,
    y los tubos y barras de la pieza de encima son tangentes a ese cilindro
    por diseno. Con ese redondeo el dintel 1x4 de la casita pisaba 0.15 mm el
    stud de abajo (20 pares de caras con 1 micra de separacion).
    """
    capa = bm.edges.layers.float.get(CAPA_BISEL) or bm.edges.layers.float.new(CAPA_BISEL)
    for e in bm.edges:
        convexa = e.is_manifold and e.calc_face_angle_signed(0.0) > ANGULO_NITIDO
        e[capa] = 1.0 if convexa else 0.0


def crear_malla(pieza: Pieza, nombre: str | None = None):
    """Crea (o reutiliza) un ``bpy.types.Mesh`` para ``pieza``."""
    nombre = nombre or f"Malla_{pieza.clave}"
    existente = bpy.data.meshes.get(nombre)
    if existente is not None:
        return existente
    bm = construir_bmesh(plan_pieza(pieza))
    malla = bpy.data.meshes.new(nombre)
    bm.to_mesh(malla)
    bm.free()
    malla.set_sharp_from_angle(angle=ANGULO_NITIDO)
    malla["bloques3d_pieza"] = pieza.clave
    return malla


def anadir_bisel(obj) -> None:
    """Bisel suave en las aristas convexas vivas, con normales endurecidas.

    ``harden_normals`` mantiene planas las caras grandes y deja redondeado
    solo el bisel, que es como se ve el ABS inyectado.
    """
    mod = obj.modifiers.new("Bisel", "BEVEL")
    mod.width = BISEL_MM
    mod.segments = BISEL_SEGMENTOS
    mod.limit_method = "WEIGHT"
    mod.edge_weight = CAPA_BISEL
    mod.use_clamp_overlap = True
    mod.harden_normals = True


def crear_objeto(pieza: Pieza, nombre: str, coleccion=None, bisel: bool = True):
    """Crea un objeto con la malla de ``pieza`` y lo enlaza a ``coleccion``."""
    obj = bpy.data.objects.new(nombre, crear_malla(pieza))
    (coleccion or bpy.context.scene.collection).objects.link(obj)
    if bisel:
        anadir_bisel(obj)
    obj["bloques3d_pieza"] = pieza.clave
    return obj


def aristas_no_manifold(malla) -> int:
    """Cuenta aristas que no comparten exactamente 2 caras."""
    bm = bmesh.new()
    bm.from_mesh(malla)
    n = sum(1 for e in bm.edges if not e.is_manifold)
    bm.free()
    return n
