# Historial: la sesión original con BlenderMCP

Esta carpeta guarda **tal cual** cómo se hizo la primera versión del proyecto,
para poder compararla. **No se mantiene** ni forma parte del generador actual
(`python -m bloques3d`, ver el [README](../README.md)).

| Archivo | Qué es |
|---|---|
| `chunk1_setup.py` … `chunk13_package.py` | Los 13 trozos de código que se mandaron, uno detrás de otro, a un Blender abierto con el addon BlenderMCP (puerto 9876) mediante `_tools/bclient.py`. Es un registro de sesión, no un programa: cada trozo depende del estado que dejó el anterior (el 3 crea bloques lisos que el 8 borra, la cámara se recoloca en el 4, 5, 8, 10 y 12). |
| `bloques_original.blend` | El `.blend` que produjo esa sesión (antes estaba en `blend/bloques.blend`). |

## Por qué se sustituyó

Medido con Blender 5.2.1 en modo `--background --factory-startup`:

- **No se puede reproducir.** Los scripts escriben en rutas fijas de
  `C:/Claude Ideas/Bloques3D/`. Al repetirlos en orden en otra máquina fallan 5 de 13:
  el 6 no puede escribir `bloques.blend`, y el 7, 11, 12 y 13 intentan guardar
  un archivo que nunca se guardó.
- **Los ladrillos flotan 4.8 mm.** En `chunk8_lego.py`, `transform_apply(scale=True)`
  también aplica posición y rotación (los dos valen `True` por defecto). La malla
  queda en z ∈ [0, 1.14] y después se suma `location.z = H/2`.
- **El "encaje" atraviesa las piezas.** Los ladrillos son cajas macizas. Los studs
  del azul se meten hasta 1.8 mm en el cuerpo del blanco, y con 1 micra de
  separación todavía se cruzan 8 pares de caras.
- **El render corta piezas.** Los studs del blanco se salen por arriba (v = 1.05)
  y el frente del rojo por abajo (v = −0.04).

Los cuatro fallos se comprueban automáticamente sobre `bloques_original.blend`:

```bash
python -m bloques3d comprobar historial/bloques_original.blend \
    --piezas Brick_Blue,Brick_White,Brick_Red --suelo Brick_Blue,Brick_Red
```

La prueba `test_el_comprobador_detecta_los_fallos_de_la_escena_original` lo
ejecuta en cada pasada, así que también demuestra que el comprobador detecta
fallos reales.
