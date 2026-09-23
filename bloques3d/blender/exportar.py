"""Exportaciones: STL por pieza (mm), GLB de la escena y video giratorio MP4."""
from __future__ import annotations

import math
from pathlib import Path

import bpy
from mathutils import Vector

from ..encuadre import direccion_camara
from ..medidas import Pieza
from . import malla


def _solo_seleccionado(objetos) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objetos:
        o.select_set(True)
    if objetos:
        bpy.context.view_layer.objects.active = objetos[0]


def exportar_stl(piezas: list[Pieza], carpeta: Path) -> list[str]:
    """Un STL binario por tipo de pieza, en milimetros y sin girar.

    Se exporta la malla evaluada (con el bisel), que sigue siendo cerrada:
    cada arista la comparten exactamente dos triangulos.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = []
    for pieza in piezas:
        obj = malla.crear_objeto(pieza, f"STL_{pieza.clave}")
        bpy.context.view_layer.update()
        _solo_seleccionado([obj])
        ruta = carpeta / f"{pieza.clave}.stl"
        resultado = bpy.ops.wm.stl_export(
            filepath=str(ruta),
            export_selected_objects=True,
            ascii_format=False,
            apply_modifiers=True,
            global_scale=1.0,
            use_scene_unit=False,   # 1 unidad = 1 mm, sin reescalar
            forward_axis="Y",
            up_axis="Z",
        )
        bpy.data.objects.remove(obj, do_unlink=True)
        if "FINISHED" not in resultado or not ruta.exists():
            raise RuntimeError(f"no se pudo exportar {ruta}")
        salida.append(str(ruta))
    return salida


def exportar_glb(objetos, ruta: Path) -> str:
    """GLB con una malla por pieza, en metros (la unidad de glTF).

    La escena vive en mm, asi que se cuelgan las piezas de un vacio con
    escala 0.001 solo durante la exportacion.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    raiz = bpy.data.objects.new("bloques3d", None)
    bpy.context.scene.collection.objects.link(raiz)
    raiz.scale = (0.001, 0.001, 0.001)
    padres = {}
    for o in objetos:
        padres[o.name] = (o.parent, o.matrix_world.copy())
        o.parent = raiz
        o.matrix_parent_inverse.identity()
    bpy.context.view_layer.update()
    _solo_seleccionado([raiz, *objetos])
    try:
        resultado = bpy.ops.export_scene.gltf(
            filepath=str(ruta),
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_yup=True,
            export_cameras=False,
            export_lights=False,
            export_animations=False,
            export_extras=True,
        )
    finally:
        for o in objetos:
            padre, mundo = padres[o.name]
            o.parent = padre
            o.matrix_world = mundo
        bpy.data.objects.remove(raiz, do_unlink=True)
    if "FINISHED" not in resultado or not ruta.exists():
        raise RuntimeError(f"no se pudo exportar {ruta}")
    return str(ruta)


def preparar_giro(scene, cam, centro: Vector, distancia: float, azimut: float, elevacion: float,
                  fotogramas: int, fps: int = 24):
    """Cuelga la camara de un pivote y le da una vuelta completa en bucle.

    El fotograma ``fotogramas + 1`` coincidiria con el 1, asi que el video
    termina uno antes y el bucle no repite imagen.
    """
    pivote = bpy.data.objects.new("Pivote_Giro", None)
    scene.collection.objects.link(pivote)
    pivote.location = centro
    bpy.context.view_layer.update()
    # Como en una plataforma giratoria real (la pieza gira bajo luces fijas):
    # camara y luces orbitan juntas, asi la iluminacion no cambia en el video.
    inversa = pivote.matrix_world.inverted()
    for luz in [o for o in scene.objects if o.type == "LIGHT"]:
        luz.parent = pivote
        luz.matrix_parent_inverse = inversa
    cam.parent = pivote
    cam.matrix_parent_inverse.identity()
    cam.location = Vector(direccion_camara(azimut, elevacion)) * distancia
    cam.rotation_euler = (-cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.dof.use_dof = False

    scene.frame_start, scene.frame_end = 1, fotogramas
    scene.render.fps = fps
    pivote.rotation_euler = (0.0, 0.0, 0.0)
    pivote.keyframe_insert("rotation_euler", index=2, frame=1)
    pivote.rotation_euler = (0.0, 0.0, 2 * math.pi)
    pivote.keyframe_insert("rotation_euler", index=2, frame=fotogramas + 1)
    # Blender 5.x: acciones por capas; las F-curves viven en el channelbag del slot.
    anim = pivote.animation_data
    bolsa = anim.action.layers[0].strips[0].channelbag(anim.action_slot)
    for fc in bolsa.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    return pivote


def render_giro(scene, ruta: Path) -> str:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ims = scene.render.image_settings
    ims.media_type = "VIDEO"          # Blender 5.x: antes que file_format
    ims.file_format = "FFMPEG"
    ff = scene.render.ffmpeg
    ff.format = "MPEG4"
    ff.codec = "H264"
    ff.constant_rate_factor = "HIGH"
    ff.ffmpeg_preset = "GOOD"
    ff.audio_codec = "NONE"
    scene.render.use_file_extension = True
    scene.render.filepath = str(ruta)
    bpy.ops.render.render(animation=True)
    if not ruta.exists():
        raise RuntimeError(f"Blender no escribio el video en {ruta}")
    return str(ruta)
