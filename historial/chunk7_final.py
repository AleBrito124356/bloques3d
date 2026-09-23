import bpy
import time

scene = bpy.context.scene
cam = bpy.data.objects["Camera"]
cam.data.lens = 58          # un poco mas de aire alrededor de los bloques

scene.render.resolution_x = 2560
scene.render.resolution_y = 1440
scene.render.filepath = "C:/Claude Ideas/Bloques3D/render/bloques_render.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print("Render final OK en %.1fs" % (time.time() - t0))

bpy.ops.wm.save_mainfile()
print("Blend guardado.")
