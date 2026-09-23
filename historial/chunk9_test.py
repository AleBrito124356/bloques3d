import bpy
import time

scene = bpy.context.scene
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.filepath = "C:/Claude Ideas/Bloques3D/render/_test.png"
t0 = time.time()
bpy.ops.render.render(write_still=True)
print("Test render OK en %.1fs" % (time.time() - t0))
