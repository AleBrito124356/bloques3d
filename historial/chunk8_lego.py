import bpy
import math
import mathutils

# ---- Quitar los bloques lisos anteriores ----
for n in ("Block_Ivory", "Block_Blue", "Block_Red"):
    o = bpy.data.objects.get(n)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
for me in list(bpy.data.meshes):
    if me.users == 0:
        bpy.data.meshes.remove(me)

# ---- Materiales: subir brillo a plastico ABS tipo LEGO ----
for mname, rough in (("Mat_Ivory", 0.18), ("Mat_Blue", 0.13), ("Mat_Red", 0.14)):
    b = bpy.data.materials[mname].node_tree.nodes.get("Principled BSDF")
    b.inputs["Roughness"].default_value = rough
    for k, v in (("Coat Weight", 0.5), ("Coat Roughness", 0.06),
                 ("Clearcoat", 0.5), ("Clearcoat Roughness", 0.06)):
        try:
            b.inputs[k].default_value = v
        except Exception:
            pass

# ---- Generador de brick LEGO 2x4 (1 unidad = 10 mm) ----
L, W, H = 3.2, 1.6, 0.96          # cuerpo
SR, SH = 0.24, 0.18               # stud: radio y alto
PITCH = 0.8

def make_brick(name, matname):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, H / 2))
    body = bpy.context.active_object
    body.name = name
    body.scale = (L, W, H)
    bpy.ops.object.transform_apply(scale=True)
    studs = []
    for x in (-1.5 * PITCH, -0.5 * PITCH, 0.5 * PITCH, 1.5 * PITCH):
        for y in (-0.5 * PITCH, 0.5 * PITCH):
            bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=SR, depth=SH,
                                                location=(x, y, H + SH / 2))
            studs.append(bpy.context.active_object)
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True)
    for s in studs:
        s.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.join()
    bev = body.modifiers.new("Bevel", 'BEVEL')
    bev.width = 0.018
    bev.segments = 3
    bev.limit_method = 'ANGLE'
    bev.angle_limit = math.radians(40)
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(35))
    except Exception:
        pass
    body.data.materials.append(bpy.data.materials[matname])
    return body

blue = make_brick("Brick_Blue", "Mat_Blue")
white = make_brick("Brick_White", "Mat_Ivory")
red = make_brick("Brick_Red", "Mat_Red")

# ---- Posiciones ----
TH = math.radians(-4)
blue.location = (0.1, -0.1, H / 2)
blue.rotation_euler = (0, 0, TH)

# Blanco MEDIO MONTADO sobre el azul: encajado en su rejilla de studs
# (misma rotacion, desplazado 2 studs a lo largo y 1 fila lateral)
off = mathutils.Matrix.Rotation(TH, 4, 'Z') @ mathutils.Vector((-2 * PITCH, PITCH, 0))
white.location = (blue.location[0] + off.x, blue.location[1] + off.y, H + H / 2 - 0.002)
white.rotation_euler = (0, 0, TH)

red.location = (2.5, -1.55, H / 2)
red.rotation_euler = (0, 0, math.radians(7))

# Recentrar camara al nuevo conjunto (mas alto por el apilado)
cam = bpy.data.objects["Camera"]
cam.location = (4.8, -8.8, 6.4)
d = mathutils.Vector((0.0, -0.05, 0.55)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.focus_object = blue

print("LEGO bricks OK")
