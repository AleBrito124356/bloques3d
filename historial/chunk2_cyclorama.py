import bpy
import math

# Perfil del ciclorama: suelo plano -> arco de radio R -> pared vertical
Y0, R, H, W = 2.0, 3.5, 9.0, 12.0   # inicio del arco, radio, alto pared, semiancho
profile = [(-10.0, 0.0), (Y0, 0.0)]
ARC_SEGS = 18
for i in range(1, ARC_SEGS + 1):
    t = (i / ARC_SEGS) * (math.pi / 2)
    profile.append((Y0 + R * math.sin(t), R - R * math.cos(t)))
profile.append((Y0 + R, H))

verts, faces = [], []
for (y, z) in profile:
    verts.append((-W, y, z))
    verts.append((W, y, z))
for i in range(len(profile) - 1):
    a = i * 2
    faces.append((a, a + 1, a + 3, a + 2))

mesh = bpy.data.meshes.new("Cyclorama")
mesh.from_pydata(verts, [], faces)
mesh.update()
cyc = bpy.data.objects.new("Cyclorama", mesh)
bpy.context.collection.objects.link(cyc)
for p in mesh.polygons:
    p.use_smooth = True

m = bpy.data.materials.new("Mat_Studio_White")
m.use_nodes = True
b = m.node_tree.nodes.get("Principled BSDF")
b.inputs["Base Color"].default_value = (0.93, 0.93, 0.94, 1)
b.inputs["Roughness"].default_value = 0.42
cyc.data.materials.append(m)

print("Cyclorama OK | verts:", len(verts), "faces:", len(faces))
