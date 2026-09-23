import bpy

# Limpiar escena por defecto
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
    for b in list(coll):
        if b.users == 0:
            coll.remove(b)

scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
try:
    scene.eevee.taa_render_samples = 128
except Exception as e:
    print("samples:", e)
for attr in ("use_raytracing", "use_fast_gi"):
    try:
        setattr(scene.eevee, attr, True)
    except Exception as e:
        print("skip", attr, e)

# View transform: PBR Neutral (ideal para product shots) con fallback a Standard
try:
    scene.view_settings.view_transform = 'Khronos PBR Neutral'
except Exception:
    try:
        scene.view_settings.view_transform = 'Standard'
    except Exception as e:
        print("vt:", e)
scene.view_settings.exposure = 0.0

# Mundo blanco suave (relleno ambiental)
world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
bgn = world.node_tree.nodes.get("Background")
if bgn:
    bgn.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bgn.inputs["Strength"].default_value = 0.45

print("Setup OK | engine:", scene.render.engine, "| vt:", scene.view_settings.view_transform)
