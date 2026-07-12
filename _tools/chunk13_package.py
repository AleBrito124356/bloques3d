import bpy
import os

# Ruta de render relativa al .blend (funciona en cualquier PC)
bpy.context.scene.render.filepath = "//bloques_render.png"

# Empaquetar cualquier recurso externo dentro del .blend (autocontenido)
try:
    bpy.ops.file.pack_all()
    print("pack_all OK")
except Exception as e:
    print("pack_all:", e)

# Guardar el archivo de trabajo y una copia limpia en la carpeta de entrega
bpy.ops.wm.save_mainfile()
out = "C:/Claude Ideas/Bloques3D/entrega/Bloques_LEGO_Blender/bloques.blend"
os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
print("Copia de entrega guardada en:", out)
