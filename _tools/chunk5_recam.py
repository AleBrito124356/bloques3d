import bpy
import mathutils

cam = bpy.data.objects["Camera"]
cam.location = (4.6, -8.6, 6.6)
cam.data.lens = 65
d = mathutils.Vector((0.0, -0.05, 0.2)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
cam.data.dof.aperture_fstop = 5.6

print("Recam OK")
