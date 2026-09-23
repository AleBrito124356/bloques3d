import bpy
import mathutils
import math

def aim(ob, target):
    d = mathutils.Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def area_light(name, loc, size, power, color=(1, 1, 1), target=(0, 0, 0.4)):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.size = size
    data.color = color
    ob = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(ob)
    ob.location = loc
    aim(ob, target)
    return ob

# Key calida grande (arriba-izquierda-frente): sombras suaves direccionales
area_light("Key",  (-5.0, -4.0, 6.5), 4.5, 700, (1.0, 0.97, 0.93))
# Relleno frio tenue (derecha): levanta las sombras sin matarlas
area_light("Fill", (6.0, -5.0, 3.2), 3.0, 160, (0.93, 0.95, 1.0))
# Contraluz (atras-arriba): borde brillante que separa los bloques del fondo
area_light("Rim",  (0.5, 6.0, 6.5), 5.0, 420, (1.0, 1.0, 1.0))

# Camara 50mm, 3/4 elevada, con DOF sutil enfocado al bloque azul
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 50
cam = bpy.data.objects.new("Camera", cam_data)
bpy.context.collection.objects.link(cam)
cam.location = (3.4, -7.2, 4.4)
aim(cam, (0.05, -0.15, 0.30))
cam_data.dof.use_dof = True
cam_data.dof.focus_object = bpy.data.objects["Block_Blue"]
cam_data.dof.aperture_fstop = 4.0
bpy.context.scene.camera = cam

# Viewport a vista de camara + material preview
for win in bpy.context.window_manager.windows:
    for ar in win.screen.areas:
        if ar.type == 'VIEW_3D':
            for sp in ar.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = 'MATERIAL'
                    sp.region_3d.view_perspective = 'CAMERA'

print("Luces y camara OK")
