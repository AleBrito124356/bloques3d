import bpy
import math
import mathutils

# Separar el rojo (tocaba la esquina del azul)
red = bpy.data.objects["Brick_Red"]
red.location = (2.85, -1.9, red.location[2])
red.rotation_euler = (0, 0, math.radians(9))

# Camara: mas atras y recentrada al conjunto completo
cam = bpy.data.objects["Camera"]
cam.location = (6.2, -10.5, 7.3)
d = mathutils.Vector((0.6, -0.3, 0.5)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

print("Fix OK")
