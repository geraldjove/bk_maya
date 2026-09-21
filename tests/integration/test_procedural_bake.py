"""blender --background --factory-startup --python tests/integration/test_procedural_bake.py"""

import importlib.util
import tempfile
from pathlib import Path

import bpy

script = Path(__file__).resolve().parents[2] / "bk_maya/scripts/export_usd.py"
spec = importlib.util.spec_from_file_location("export_usd", script)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
obj = bpy.data.objects["Cube"]
mat = bpy.data.materials.new("ProceduralTest")
mat.use_nodes = True
obj.data.materials.clear()
obj.data.materials.append(mat)
tree = mat.node_tree
shader = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
noise = tree.nodes.new("ShaderNodeTexNoise")
tree.links.new(noise.outputs["Color"], shader.inputs["Base Color"])
tree.links.new(noise.outputs["Fac"], shader.inputs["Roughness"])
points = [tuple(v.co) for v in obj.data.vertices]
with tempfile.TemporaryDirectory(prefix="blendkit-bake-test-") as folder:
    exporter._bake_preview_materials(str(Path(folder) / "test.usd"), 128)
    assert [tuple(v.co) for v in obj.data.vertices] == points
    assert len(obj.data.uv_layers) == 1
    assert obj.data.uv_layers.active.name == "BK_Bake"
    assert len({tuple(v.uv) for v in obj.data.uv_layers.active.data}) > 8
    baked = obj.data.materials[0]
    assert baked != mat and shader.inputs["Base Color"].links[0].from_node == noise
    principal = next(n for n in baked.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for channel in ("Base Color", "Roughness"):
        node = principal.inputs[channel].links[0].from_node
        assert node.type == "TEX_IMAGE"
        assert Path(node.image.filepath_raw).is_file()
        pixels = list(node.image.pixels)[::4]
        assert max(pixels) - min(pixels) > 0.1, "Procedural detail must survive the bake"
print("PASS: procedural channels baked to nonuniform textures with valid UVs and unchanged geometry/source material")

# The pencil's legacy Glossy mix previously exported no usable surface at all.
legacy = bpy.data.materials.new("LegacySteel")
legacy.use_nodes = True
tree = legacy.node_tree
tree.nodes.remove(next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED"))
output = next(n for n in tree.nodes if n.type == "OUTPUT_MATERIAL")
glossy = tree.nodes.new("ShaderNodeBsdfGlossy")
glossy.inputs["Roughness"].default_value = 0.3
polished = tree.nodes.new("ShaderNodeBsdfGlossy")
mix = tree.nodes.new("ShaderNodeMixShader")
tree.links.new(glossy.outputs[0], mix.inputs[1])
tree.links.new(polished.outputs[0], mix.inputs[2])
tree.links.new(mix.outputs[0], output.inputs["Surface"])
noise = tree.nodes.new("ShaderNodeTexNoise")
tree.links.new(noise.outputs["Fac"], glossy.inputs["Color"])
obj.data.materials[0] = legacy
with tempfile.TemporaryDirectory(prefix="blendkit-glossy-test-") as folder:
    exporter._bake_preview_materials(str(Path(folder) / "test.usd"), 128)
    converted = obj.data.materials[0]
    principal = next(n for n in converted.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    assert principal.inputs["Metallic"].default_value == 1.0
    assert abs(principal.inputs["Roughness"].default_value - 0.3) < 1e-6
    image = principal.inputs["Base Color"].links[0].from_node.image
    assert Path(image.filepath_raw).is_file()
    pixels = list(image.pixels)[::4]
    assert max(pixels) - min(pixels) > 0.1
    assert not any(n.type == "BSDF_PRINCIPLED" for n in legacy.node_tree.nodes)
print("PASS: legacy Glossy mix exports a textured metal surface without editing its source material")
