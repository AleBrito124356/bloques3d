"""Estudio fotografico: unidades, motor, materiales ABS, ciclorama, luces y camara.

Todo se crea con ``bpy.data`` (sin operadores), asi que funciona igual en
``blender --background --factory-startup`` que en una sesion con ventana.
La escena trabaja en milimetros: 1 unidad de Blender = 1 mm y la escala de
unidades es 0.001, de modo que la interfaz de Blender muestra "mm".
"""
from __future__ import annotations

import math

import bmesh
import bpy
from mathutils import Matrix, Vector

from ..encuadre import Encuadre, direccion_camara
from ..paleta import ColorABS, srgb_a_lineal

MOTORES = {"eevee": "BLENDER_EEVEE", "cycles": "CYCLES"}
# Irradiancia objetivo (W/m^2) de cada luz en el centro de la escena.
IRRADIANCIA = {"principal": 3.2, "relleno": 0.55, "contraluz": 2.2, "mundo": 0.10}
EXPOSICION = {"eevee": 0.0, "cycles": -0.4}


# --- Escena y motor -------------------------------------------------------------------

def vaciar_escena() -> None:
    """Borra todo lo que trae la escena de fabrica (cubo, luz, camara)."""
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coleccion in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras,
                      bpy.data.curves):
        for dato in list(coleccion):
            if dato.users == 0:
                coleccion.remove(dato)


def configurar_unidades(scene) -> None:
    us = scene.unit_settings
    us.system = "METRIC"
    us.scale_length = 0.001
    us.length_unit = "MILLIMETERS"


def configurar_render(scene, motor: str, ancho: int, alto: int, muestras: int) -> None:
    if motor not in MOTORES:
        raise ValueError(f"motor desconocido {motor!r}; usa {', '.join(MOTORES)}")
    r = scene.render
    r.engine = MOTORES[motor]
    r.resolution_x, r.resolution_y = ancho, alto
    r.resolution_percentage = 100
    r.film_transparent = False
    if motor == "eevee":
        ee = scene.eevee
        ee.taa_render_samples = muestras
        ee.use_raytracing = True
        ee.ray_tracing_method = "SCREEN"
        ee.use_shadows = True
        ee.use_fast_gi = True
        ee.fast_gi_method = "GLOBAL_ILLUMINATION"
        ee.shadow_ray_count = 2       # penumbras suaves con menos grano
        ee.shadow_step_count = 12
    else:
        cy = scene.cycles
        cy.device = "CPU"
        cy.samples = muestras
        cy.use_adaptive_sampling = True
        cy.use_denoising = True
        cy.denoiser = "OPENIMAGEDENOISE"
        cy.max_bounces = 8
        cy.transmission_bounces = 8
    vs = scene.view_settings
    for vista in ("Khronos PBR Neutral", "AgX"):
        try:
            vs.view_transform = vista
            break
        except TypeError:
            continue
    vs.look = "None"
    # Cycles suma mas luz rebotada del fondo blanco: se compensa para que el
    # ladrillo blanco no pierda el detalle de los studs.
    vs.exposure = EXPOSICION[motor]
    vs.gamma = 1.0


def configurar_salida_imagen(scene, formato: str = "PNG") -> None:
    ims = scene.render.image_settings
    ims.media_type = "IMAGE"          # Blender 5.x: antes que file_format
    ims.file_format = formato
    if formato == "PNG":
        ims.color_mode = "RGB"
        ims.color_depth = "8"
        ims.compression = 90
    elif formato == "JPEG":
        ims.color_mode = "RGB"
        ims.quality = 90


# --- Materiales ------------------------------------------------------------------------

def material_abs(color: ColorABS):
    """Plastico ABS inyectado: base brillante + capa de barniz (coat) fina."""
    nombre = f"ABS_{color.nombre}"
    mat = bpy.data.materials.get(nombre)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(nombre)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color.lineal, 1.0)
    bsdf.inputs["Roughness"].default_value = color.rugosidad
    bsdf.inputs["IOR"].default_value = 1.54            # ABS
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    bsdf.inputs["Coat Weight"].default_value = 0.25
    bsdf.inputs["Coat Roughness"].default_value = 0.06
    if color.transparente:
        bsdf.inputs["Transmission Weight"].default_value = 1.0
        bsdf.inputs["IOR"].default_value = 1.58        # policarbonato
        bsdf.inputs["Coat Weight"].default_value = 0.0
        mat.use_raytrace_refraction = True
        mat.thickness_mode = "SLAB"
    mat.diffuse_color = (*color.lineal, 1.0)            # color en el viewport solido
    mat["bloques3d_color"] = color.nombre
    return mat


def material_fondo(hex_color: str):
    h = hex_color.lstrip("#")
    lin = tuple(srgb_a_lineal(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    mat = bpy.data.materials.new("Estudio_Fondo")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*lin, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Specular IOR Level"].default_value = 0.3
    return mat, lin


# --- Ciclorama, mundo y luces ----------------------------------------------------------

def ciclorama(centro: Vector, radio_suelo: float, curva: float, hex_color: str, coleccion,
              segmentos: int = 96):
    """Fondo infinito "de cuenco": suelo plano que se curva en pared alrededor.

    Es de revolucion, asi que se ve igual desde cualquier azimut (lo necesita
    el video giratorio) y deja dentro camara y luces. El suelo esta
    exactamente en z = 0.
    """
    perfil = [(radio_suelo, 0.0)]
    pasos_arco = 16
    for i in range(1, pasos_arco + 1):
        t = (i / pasos_arco) * (math.pi / 2)
        perfil.append((radio_suelo + curva * math.sin(t), curva - curva * math.cos(t)))
    perfil.append((radio_suelo + curva, curva + 3.0 * radio_suelo))

    bm = bmesh.new()
    anillos = []
    for r, z in perfil:
        anillos.append([
            bm.verts.new((r * math.cos(2 * math.pi * k / segmentos), r * math.sin(2 * math.pi * k / segmentos), z))
            for k in range(segmentos)
        ])
    suelo = bm.faces.new(anillos[0])
    suelo.smooth = False
    for a, b in zip(anillos, anillos[1:]):
        for k in range(segmentos):
            f = bm.faces.new((a[k], a[(k + 1) % segmentos], b[(k + 1) % segmentos], b[k]))
            f.smooth = True
    for f in bm.faces:  # normales hacia dentro del cuenco (hacia la escena)
        f.normal_update()
        centro_cara = f.calc_center_median()
        hacia_eje = Vector((-centro_cara.x, -centro_cara.y, 0.0))
        if f.normal.dot(Vector((0, 0, 1)) if f is suelo else hacia_eje) < 0:
            f.normal_flip()
    malla = bpy.data.meshes.new("Ciclorama")
    bm.to_mesh(malla)
    bm.free()
    mat, _ = material_fondo(hex_color)
    malla.materials.append(mat)
    obj = bpy.data.objects.new("Ciclorama", malla)
    obj.location = (centro.x, centro.y, 0.0)
    coleccion.objects.link(obj)
    return obj


def mundo(hex_color: str, fuerza: float = IRRADIANCIA["mundo"]):
    h = hex_color.lstrip("#")
    lin = tuple(srgb_a_lineal(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    w = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    w.use_nodes = True
    fondo = w.node_tree.nodes.get("Background")
    fondo.inputs["Color"].default_value = (*lin, 1.0)
    fondo.inputs["Strength"].default_value = fuerza
    bpy.context.scene.world = w
    return w


def _apuntar(obj, objetivo: Vector) -> None:
    obj.rotation_euler = (objetivo - obj.location).to_track_quat("-Z", "Y").to_euler()


def luces_tres_puntos(centro: Vector, radio: float, azimut: float, coleccion) -> list:
    """Principal calida, relleno frio y contraluz, relativas a la camara.

    Blender mide la potencia en W con 1 unidad = 1 m para la caida de luz,
    asi que en una escena en mm la potencia se fija por la irradiancia
    deseada en el centro: ``P = E * pi * d^2``. Asi la exposicion no depende
    del tamano de la escena.
    """
    esquema = (
        # nombre, azimut relativo, elevacion, distancia (radios), tamano (radios), irradiancia, color
        ("Luz_Principal", -55.0, 55.0, 6.0, 2.0, IRRADIANCIA["principal"], (1.0, 0.95, 0.89)),
        ("Luz_Relleno", 75.0, 20.0, 7.0, 4.0, IRRADIANCIA["relleno"], (0.90, 0.94, 1.0)),
        ("Luz_Contraluz", 170.0, 45.0, 6.0, 3.0, IRRADIANCIA["contraluz"], (1.0, 1.0, 1.0)),
    )
    luces = []
    for nombre, daz, elev, dist, tam, irradiancia, rgb in esquema:
        datos = bpy.data.lights.new(nombre, "AREA")
        datos.shape = "DISK"
        datos.size = tam * radio
        datos.energy = irradiancia * math.pi * (dist * radio) ** 2
        datos.use_shadow_jitter = nombre == "Luz_Principal"   # EEVEE: penumbra fisica
        datos.color = rgb
        obj = bpy.data.objects.new(nombre, datos)
        obj.location = centro + Vector(direccion_camara(azimut + daz, elev)) * dist * radio
        _apuntar(obj, centro)
        coleccion.objects.link(obj)
        luces.append(obj)
    return luces


def camara(enc: Encuadre, coleccion, apertura: float | None = None, foco_mm: float | None = None):
    datos = bpy.data.cameras.new("Camara")
    datos.lens = enc.lente
    datos.sensor_width = enc.sensor
    datos.sensor_fit = "AUTO"
    obj = bpy.data.objects.new("Camara", datos)
    obj.location = enc.posicion
    obj.rotation_euler = Matrix(enc.matriz_rotacion()).to_euler("XYZ")
    distancia = Vector(enc.posicion).length
    datos.clip_start = 1.0
    datos.clip_end = max(10000.0, distancia * 50)
    if apertura is not None:
        datos.dof.use_dof = True
        # Blender calcula el diametro de apertura como lente*1e-3/f, es decir,
        # suponiendo 1 unidad = 1 m, y no aplica scale_length (medido en 5.2:
        # f/1.4 salia totalmente nitido). Con la escena en mm hay que dividir
        # el numero f entre 1000 para que el desenfoque sea el de una camara
        # real a esa distancia. El valor "de verdad" queda como propiedad.
        datos.dof.aperture_fstop = apertura * bpy.context.scene.unit_settings.scale_length
        datos.dof.focus_distance = foco_mm if foco_mm is not None else distancia
        datos["bloques3d_numero_f"] = apertura
    coleccion.objects.link(obj)
    bpy.context.scene.camera = obj
    return obj
