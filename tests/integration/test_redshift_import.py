"""Run with Maya's mayapy and the MayaUSD/Redshift plug-ins installed.

    mayapy tests/integration/test_redshift_import.py

Uses a temporary USD and a separate standalone scene; no downloads or saved
user scenes are needed. Set REDSHIFT_MAYA_PLUGIN to a plug-in path if needed.
"""

import os
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "bk_maya/lib")]


def make_usd(folder, multi=True):
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdShade

    image = folder / "texture.bmp"
    image.write_bytes(
        b"BM"
        + struct.pack("<IHHI", 58, 0, 0, 54)
        + struct.pack("<IiiHHIIiiII", 40, 1, 1, 1, 24, 0, 4, 0, 0, 0, 0)
        + bytes((128, 128, 255, 0))
    )
    path = folder / ("model.usda" if multi else "material.usda")
    stage = Usd.Stage.CreateNew(str(path))
    root = UsdGeom.Xform.Define(stage, "/Asset")
    stage.SetDefaultPrim(root.GetPrim())
    UsdGeom.SetStageUpAxis(stage, "Y")
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)
    mesh = UsdGeom.Mesh.Define(stage, "/Asset/Mesh")
    mesh.CreatePointsAttr([(-1, 0, -1), (-1, 0, 1), (1, 0, 1), (1, 0, -1)])
    mesh.CreateFaceVertexCountsAttr([3, 3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2, 0, 2, 3])
    mesh.CreateSubdivisionSchemeAttr("none")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).SetMaterialBindSubsetsFamilyType("partition")
    UsdGeom.PrimvarsAPI(mesh).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, "vertex").Set(
        [(0, 0), (0, 1), (1, 1), (1, 0)]
    )
    for index, name in enumerate(("Paint", "Metal") if multi else ("Paint",)):
        material = UsdShade.Material.Define(stage, f"/Asset/{name}")
        shader = UsdShade.Shader.Define(stage, f"/Asset/{name}/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.2, 0.4, 0.6))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.35)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(index))
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.8)
        shader.CreateInput("ior", Sdf.ValueTypeNames.Float).Set(1.45)
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        if not index:
            uv = UsdShade.Shader.Define(stage, f"/Asset/{name}/UV")
            uv.CreateIdAttr("UsdPrimvarReader_float2")
            uv.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
            uv.CreateOutput("result", Sdf.ValueTypeNames.Float2)
            for input_name, channel, value_type in (
                ("diffuseColor", "rgb", Sdf.ValueTypeNames.Color3f),
                ("roughness", "r", Sdf.ValueTypeNames.Float),
                ("normal", "rgb", Sdf.ValueTypeNames.Normal3f),
            ):
                texture = UsdShade.Shader.Define(stage, f"/Asset/{name}/{input_name}")
                texture.CreateIdAttr("UsdUVTexture")
                texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath("./texture.bmp"))
                texture.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.Token).Set(
                    "sRGB" if input_name == "diffuseColor" else "raw"
                )
                texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(uv.ConnectableAPI(), "result")
                if input_name == "normal":
                    texture.CreateInput("scale", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(2, 2, 2, 1))
                    texture.CreateInput("bias", Sdf.ValueTypeNames.Float4).Set(Gf.Vec4f(-1, -1, -1, 0))
                texture.CreateOutput(
                    channel, Sdf.ValueTypeNames.Float3 if channel == "rgb" else Sdf.ValueTypeNames.Float
                )
                shader.CreateInput(input_name, value_type).ConnectToSource(texture.ConnectableAPI(), channel)
        if multi:
            subset = UsdGeom.Subset.Define(stage, f"/Asset/Mesh/{name}")
            subset.CreateElementTypeAttr("face")
            subset.CreateFamilyNameAttr("materialBind")
            subset.CreateIndicesAttr([index])
            UsdShade.MaterialBindingAPI.Apply(subset.GetPrim()).Bind(material)
        else:
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    stage.GetRootLayer().Save()
    return str(path)


def check():
    from maya import cmds

    from bk_maya.core import redshift
    from bk_maya.core.download import _DownloadController
    from bk_maya.core.prefs import prefs

    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    cmds.loadPlugin(os.environ.get("REDSHIFT_MAYA_PLUGIN", "redshift4maya"), quiet=True)
    cmds.file(new=True, force=True)
    prefs.material_target = "auto"
    cmds.setAttr("defaultRenderGlobals.currentRenderer", "mayaSoftware", type="string")
    assert not redshift.is_requested()
    cmds.setAttr("defaultRenderGlobals.currentRenderer", "redshift", type="string")
    assert redshift.is_requested()
    prefs.material_target = "maya"
    assert not redshift.is_requested()
    prefs.material_target = "auto"

    untouched = cmds.shadingNode("standardSurface", asShader=True, name="Existing")
    untouched_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name="ExistingSG")
    cmds.connectAttr(untouched + ".outColor", untouched_group + ".surfaceShader")
    controller = _DownloadController({"name": "Test"}, (0, 0, 0), 0)
    with tempfile.TemporaryDirectory(prefix="blendkit-redshift-") as folder:
        model = make_usd(Path(folder))
        prefs.import_method = "stage"
        controller._import_usd(model)
        assert not cmds.ls(type="mayaUsdProxyShape"), "Redshift must import editable geometry"
        shaders = cmds.ls(type="RedshiftStandardMaterial") or []
        assert len(shaders) == 2, shaders
        assert cmds.isConnected(untouched + ".outColor", untouched_group + ".surfaceShader")
        paint = next(s for s in shaders if cmds.getAttr(s + ".metalness") < 0.5)
        metal = next(s for s in shaders if cmds.getAttr(s + ".metalness") > 0.5)
        assert abs(cmds.getAttr(metal + ".metalness") - 1) < 1e-5
        assert abs(cmds.getAttr(metal + ".refl_roughness") - 0.35) < 1e-5
        assert all(abs(a - b) < 1e-5 for a, b in zip(cmds.getAttr(metal + ".base_color")[0], (0.2, 0.4, 0.6)))
        for attr in ("base_color", "refl_roughness"):
            connection = cmds.connectionInfo(paint + "." + attr, sourceFromDestination=True)
            assert connection, attr
            texture = connection.split(".")[0]
            assert cmds.nodeType(texture) == "file", connection
            assert Path(cmds.getAttr(texture + ".fileTextureName")).is_file()
            assert cmds.listConnections(texture + ".uvCoord", source=True, destination=False)
            space = cmds.getAttr(texture + ".colorSpace").lower()
            assert space.endswith("raw") if attr == "refl_roughness" else "srgb" in space
        bump = cmds.listConnections(paint + ".bump_input", source=True, destination=False)[0]
        assert cmds.nodeType(bump) == "RedshiftBumpMap"
        assert cmds.getAttr(bump + ".inputType") == 1
        normal_texture = cmds.listConnections(bump + ".input", source=True, destination=False)[0]
        assert cmds.getAttr(bump + ".unbiasedNormalMap"), "USD signed normals must not be decoded twice"
        assert cmds.getAttr(normal_texture + ".colorGain")[0] == (2, 2, 2)
        assert cmds.getAttr(normal_texture + ".colorOffset")[0] == (-1, -1, -1)
        normal_space = cmds.getAttr(normal_texture + ".colorSpace")
        assert normal_space.lower().endswith("raw"), normal_space
        for shader in shaders:
            groups = cmds.listConnections(shader + ".outColor", type="shadingEngine")
            assert len(groups) == 1
            members = cmds.sets(groups[0], query=True)
            assert any(".f[" in member for member in members), members

        # Reference requests also take the native conversion path.
        prefs.material_target = "redshift"
        prefs.import_method = "reference"
        controller._import_usd(model)
        assert len(cmds.ls(type="RedshiftStandardMaterial")) == 4
        assert not cmds.file(query=True, reference=True)

        target = cmds.polyCube(name="MaterialTarget")[0]
        material = make_usd(Path(folder), multi=False)
        roots = set(cmds.ls(assemblies=True))
        controller.target_mesh = target
        controller._assign_material_usd(material)
        assert set(cmds.ls(assemblies=True)) == roots, "Preview geometry must be removed"
        shape = cmds.listRelatives(target, shapes=True)[0]
        group = cmds.listConnections(shape, type="shadingEngine")[0]
        assigned = cmds.listConnections(group + ".surfaceShader", source=True, destination=False)[0]
        assert cmds.nodeType(assigned) == "RedshiftStandardMaterial"

        # Missing renderer fails before creating any imported nodes.
        before = set(cmds.ls())
        with (
            patch.object(cmds, "pluginInfo", return_value=False),
            patch.object(cmds, "loadPlugin", side_effect=RuntimeError("unavailable")),
        ):
            try:
                controller._bring_in_as_import(model)
            except RuntimeError as exc:
                assert "redshift4maya" in str(exc)
            else:
                raise AssertionError("Expected missing plug-in error")
        assert set(cmds.ls()) == before

        # Scalar connections into color channels (opacity), shared materials,
        # and Maya bump2d normals retain their original input network.
        scalar = cmds.shadingNode("file", asTexture=True)
        cmds.setAttr(scalar + ".colorSpace", "Raw", type="string")
        cmds.connectAttr(scalar + ".outAlpha", untouched + ".opacityR")
        maya_bump = cmds.shadingNode("bump2d", asUtility=True)
        cmds.setAttr(maya_bump + ".bumpInterp", 1)
        cmds.connectAttr(scalar + ".outAlpha", maya_bump + ".bumpValue")
        cmds.connectAttr(maya_bump + ".outNormal", untouched + ".normalCamera")
        shared_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
        cmds.connectAttr(untouched + ".outColor", shared_group + ".surfaceShader")
        assert redshift.convert([untouched_group, shared_group]) == 1
        converted = cmds.listConnections(shared_group + ".surfaceShader", source=True, destination=False)[0]
        assert cmds.isConnected(converted + ".outColor", untouched_group + ".surfaceShader")
        assert cmds.isConnected(scalar + ".outAlpha", converted + ".opacity_colorR")
        bump = cmds.listConnections(converted + ".bump_input", source=True, destination=False)[0]
        assert not cmds.getAttr(bump + ".unbiasedNormalMap")
        assert cmds.isConnected(scalar + ".outColor", bump + ".input")

        # Legacy Blender assets can carry zero IOR: avoid white paint in RS.
        cmds.setAttr(converted + ".refl_ior", 0)
        assert redshift.repair_invalid_ior(converted)
        assert cmds.getAttr(converted + ".refl_ior") == 1.5
        cmds.setAttr(converted + ".refl_ior", 1.33)
        assert not redshift.repair_invalid_ior(converted)
        assert abs(cmds.getAttr(converted + ".refl_ior") - 1.33) < 1e-6
        cmds.connectAttr(scalar + ".outAlpha", converted + ".refl_ior")
        assert not redshift.repair_invalid_ior(converted)
        assert cmds.isConnected(scalar + ".outAlpha", converted + ".refl_ior")

        # A failed conversion leaves the original assignment and no partial nodes.
        failed_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)
        cmds.connectAttr(untouched + ".outColor", failed_group + ".surfaceShader")
        before = set(cmds.ls())
        with patch.object(redshift, "_copy_normal", side_effect=ValueError("unsupported test normal")):
            assert redshift.convert([failed_group]) == 0
        assert set(cmds.ls()) == before
        assert cmds.isConnected(untouched + ".outColor", failed_group + ".surfaceShader")

        # Maya mode retains the stage path even while Redshift is active.
        prefs.material_target = "maya"
        prefs.import_method = "stage"
        controller._import_usd(model)
        assert len(cmds.ls(type="mayaUsdProxyShape")) == 1
    print(
        "PASS: Redshift model/material imports, textures, normals, per-face assignments, mode selection and failure handling"
    )


if __name__ == "__main__":
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        check()
    finally:
        maya.standalone.uninitialize()
