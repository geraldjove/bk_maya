"""mayapy tests/integration/test_pencil_repair.py ORIGINAL.usd UPDATED.usd

Checks the real pencil's colors, IORs, wood/steel maps, placement and Undo.
"""

import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "bk_maya/lib")]


def check(original, updated):
    from maya import cmds

    from bk_maya.core import redshift
    from bk_maya.core.download import _DownloadController
    from bk_maya.core.prefs import prefs
    from bk_maya.scripts.repair_ficus import _mesh
    from bk_maya.scripts.repair_pencil import repair

    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    cmds.loadPlugin(os.environ.get("REDSHIFT_MAYA_PLUGIN", "redshift4maya"), quiet=True)
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    prefs.material_target = "redshift"
    with patch.object(redshift, "repair_invalid_ior", return_value=False):
        _DownloadController({"name": "STAEDTLER Pencil"}, (0, 0, 0), 0)._import_usd(original)
    root = "BK_STAEDTLER_Pencil"
    cmds.xform(root, translation=(7, 4, -3), rotation=(9, 12, 15), scale=(2, 2, 2))
    cmds.select(root)
    shapes = cmds.listRelatives(root, allDescendents=True, type="mesh", fullPath=True)
    points = {s: [(p.x, p.y, p.z) for p in _mesh(s).getPoints()] for s in shapes}
    matrix = cmds.xform(root, query=True, matrix=True, worldSpace=True)
    roots = set(cmds.ls(assemblies=True))
    shaders = cmds.ls(type="RedshiftStandardMaterial")
    colors = {s: cmds.getAttr(s + ".base_color") for s in shaders}
    iors = {s: cmds.getAttr(s + ".refl_ior") for s in shaders}
    assert sum(v == 0 for v in iors.values()) == 6
    missing = [s for s in shapes if "initialShadingGroup" in cmds.listConnections(s, type="shadingEngine")]
    assert len(missing) == 1
    wood = cmds.ls(type="file")[0]
    wood_path = cmds.getAttr(wood + ".fileTextureName")
    wood_links = cmds.uvLink(query=True, texture=wood)
    unrelated = cmds.shadingNode("RedshiftStandardMaterial", asShader=True, name="Unrelated")
    cmds.setAttr(unrelated + ".refl_ior", 0)
    cmds.select(root)
    fixed = repair(root, updated)
    assert len(fixed) == 7, fixed
    assert cmds.getAttr(unrelated + ".refl_ior") == 0
    assert set(cmds.ls(assemblies=True)) == roots
    assert cmds.ls(selection=True) == [root]
    assert cmds.xform(root, query=True, matrix=True, worldSpace=True) == matrix
    for shape in shapes:
        assert max(math.dist((p.x, p.y, p.z), v) for p, v in zip(_mesh(shape).getPoints(), points[shape])) < 1e-5
        groups = cmds.listConnections(shape, type="shadingEngine")
        assert len(groups) == 1 and groups[0] != "initialShadingGroup", (shape, groups)
        shader = cmds.listConnections(groups[0] + ".surfaceShader", source=True, destination=False)[0]
        assert cmds.nodeType(shader) == "RedshiftStandardMaterial"
    for shader in shaders:
        assert cmds.getAttr(shader + ".base_color") == colors[shader]
        assert cmds.getAttr(shader + ".refl_ior") == (iors[shader] or 1.5)
    assert cmds.getAttr(wood + ".fileTextureName") == wood_path and Path(wood_path).is_file()
    assert cmds.uvLink(query=True, texture=wood) == wood_links
    steel = next(s for s in fixed if s not in shaders)
    assert cmds.getAttr(steel + ".metalness") == 1
    assert abs(cmds.getAttr(steel + ".refl_roughness") - math.sqrt(0.1)) < 1e-6
    texture = cmds.listConnections(steel + ".base_color", source=True, destination=False)[0]
    assert Path(cmds.getAttr(texture + ".fileTextureName")).is_file()
    assert len(set(zip(*_mesh(missing[0]).getUVs()))) > 10
    cmds.undo()
    for shader in shaders:
        assert cmds.getAttr(shader + ".refl_ior") == iors[shader]
    assert "initialShadingGroup" in cmds.listConnections(missing[0], type="shadingEngine")
    cmds.redo()
    assert cmds.objExists(steel)
    assert repair(root, updated) == [], "Repair must be idempotent"
    print(
        "PASS: 8 pencil materials, 6 invalid IORs repaired, wood/steel maps, unchanged geometry/colors/placement, scoped Undo/Redo"
    )


if __name__ == "__main__":
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        check(*sys.argv[1:])
    finally:
        maya.standalone.uninitialize()
