"""Se ejecuta DENTRO de Blender: abre un video y cuenta sus fotogramas."""
import json
import sys

import bpy

ruta = sys.argv[sys.argv.index("--") + 1]
clip = bpy.data.movieclips.load(ruta)
print("RESULTADO_PRUEBA " + json.dumps({"fotogramas": clip.frame_duration, "tamano": list(clip.size)}), flush=True)
