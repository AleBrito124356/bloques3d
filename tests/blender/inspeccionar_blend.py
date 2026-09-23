"""Se ejecuta DENTRO de Blender con un .blend abierto: datos para las pruebas."""
import json

import bpy

scene = bpy.context.scene
col = bpy.data.collections.get("Piezas")
rutas = [scene.render.filepath] + [i.filepath for i in bpy.data.images if i.filepath]
datos = {
    "render_filepath": scene.render.filepath,
    "scale_length": scene.unit_settings.scale_length,
    "length_unit": scene.unit_settings.length_unit,
    "motor": scene.render.engine,
    "piezas": {o.name: o.get("bloques3d_pieza") for o in (col.all_objects if col else [])},
    "rutas_absolutas": [r for r in rutas if r and not r.startswith("//")],
}
print("RESULTADO_PRUEBA " + json.dumps(datos), flush=True)
