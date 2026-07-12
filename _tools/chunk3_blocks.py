import bpy
import math

def plastic(name, color, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    # Clearcoat = sheen de plastico inyectado (nombres segun version)
    for k, v in (("Coat Weight", 0.3), ("Coat Roughness", 0.1),
                 ("Clearcoat", 0.3), ("Clearcoat Roughness", 0.1)):
        try:
            b.inputs[k].default_value = v
        except Exception:
            pass
    return m

mats = {
    "ivory": plastic("Mat_Ivory", (0.91, 0.87, 0.79), 0.30),
    "blue":  plastic("Mat_Blue",  (0.05, 0.24, 0.78), 0.22),
    "red":   plastic("Mat_Red",   (0.60, 0.035, 0.045), 0.24),
}

DIM = (2.3, 1.15, 0.78)   # largo, ancho, alto

def block(name, mat, loc_xy, rot_deg):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(loc_xy[0], loc_xy[1], DIM[2] / 2))
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = DIM
    bpy.ops.object.transform_apply(scale=True)
    ob.rotation_euler = (0, 0, math.radians(rot_deg))
    bev = ob.modifiers.new("Bevel", 'BEVEL')
    bev.width = 0.045
    bev.segments = 5
    bev.limit_method = 'ANGLE'
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(30))
    except Exception:
        bpy.ops.object.shade_smooth()
    ob.data.materials.append(mat)
    return ob

block("Block_Ivory", mats["ivory"], (-1.65, 1.45), 6.0)
block("Block_Blue",  mats["blue"],  (0.0, 0.0), -4.0)
block("Block_Red",   mats["red"],   (1.65, -1.45), 7.0)

print("Blocks OK:", [o.name for o in bpy.data.objects if o.name.startswith("Block")])
