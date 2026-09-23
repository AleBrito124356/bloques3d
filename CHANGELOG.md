# Cambios

## 1.0.0 (2026-09-23)

Se reescribe el proyecto como un generador reproducible. La versión anterior
era el registro de una sesión con BlenderMCP y no se podía repetir en otra
máquina.

### Nuevo

- Paquete `bloques3d` con piezas paramétricas de medidas reales: hueco
  inferior, tubos, barras, studs fusionados y origen en la base. Catálogo de
  serie de 12 piezas y cualquier tamaño `tipo_AxB`.
- Escenas JSON validadas (solapes, soporte por studs y formato), con errores
  en español que nombran la pieza. Tres escenas: `trio`, `casita` y `catalogo`.
- `python -m bloques3d render`: construye en Blender sin interfaz, encuadra la
  cámara sola, guarda un `.blend` portable y renderiza con EEVEE o Cycles.
- Exportación `--stl` (mm, estanco), `--glb` (un nodo por pieza) y
  `--turntable` (MP4 en bucle).
- `python -m bloques3d comprobar`: encuadre, suelo, interpenetración y mallas
  cerradas sobre cualquier `.blend`.
- `validar`, `catalogo` y `blender` en la CLI; 136 pruebas, 20 de ellas con
  Blender real.
- README, galería y paquete de entrega regenerado.

### Corregido

- Las piezas flotaban 4.8 mm sobre el suelo: ahora el punto más bajo está en
  z = 0.
- El ladrillo "encajado" atravesaba al de abajo: ahora encaja en sus studs
  sin cruzar ninguna cara.
- El render cortaba los studs del blanco y el frente del rojo: la cámara se
  encuadra sola con margen.
- `_tools/bclient.py` se caía (`UnicodeDecodeError`) cuando TCP partía un
  carácter UTF-8 entre dos paquetes.
- `entrega/LEEME.txt` decía que el render tardaba "1-2 segundos" sin más
  detalle; ahora indica el tiempo medido y en qué equipo.

### Cambios de comportamiento y de archivos

- `_tools/chunk*.py` y `blend/bloques.blend` se mueven a `historial/`, sin
  modificar y sin mantenimiento. `_tools/bclient.py` sigue en su sitio y
  admite los mismos argumentos, más `--host`/`--port`.
- `render/bloques_render.png` se elimina: era una copia exacta (4 MB) de
  `entrega/Bloques_LEGO_Blender/bloques_render.png`.
- `entrega/Bloques_LEGO_Blender/` pasa a contener `trio.blend` y `trio.jpg`,
  generados con el nuevo pipeline, en lugar de `bloques.blend` y
  `bloques_render.png`.
