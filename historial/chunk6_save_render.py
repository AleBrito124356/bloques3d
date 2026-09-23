import bpy
import time

bpy.ops.wm.save_as_mainfile(filepath="C:/Claude Ideas/Bloques3D/blend/bloques.blend")

scene = bpy.context.scene
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = "C:/Claude Ideas/Bloques3D/render/bloques_render.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print("Render OK en %.1fs" % (time.time() - t0))
