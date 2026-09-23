import bpy
import mathutils
import time

cam = bpy.data.objects["Camera"]
cam.data.lens = 54
d = mathutils.Vector((0.55, -0.2, 0.68)) - cam.location
cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

scene = bpy.context.scene
scene.render.filepath = "C:/Claude Ideas/Bloques3D/render/bloques_render.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print("Render OK en %.1fs" % (time.time() - t0))
bpy.ops.wm.save_mainfile()
print("Guardado.")
