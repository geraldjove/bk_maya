"""mayapy tests/integration/test_ficus_repair.py ORIGINAL.usda BAKED.usd

Requires the cached ficus export and its regenerated procedural bake.
Exercises real UV transfer, shader connections, placement preservation and undo.
"""

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "bk_maya/lib")]


def check(original, baked):
    from maya import cmds

    from bk_maya.core.download import _DownloadController
    from bk_maya.core.prefs import prefs
    from bk_maya.scripts.repair_ficus import MATERIALS, _materials_on, _mesh, repair

    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    cmds.loadPlugin(os.environ.get("REDSHIFT_MAYA_PLUGIN", "redshift4maya"), quiet=True)
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    prefs.material_target = "redshift"
    _DownloadController({"name": "Modular ficus plant"}, (0, 0, 0), 0)._import_usd(original)
    root = "BK_Modular_ficus_plant"
    cmds.xform(root, translation=(9, 12, -4), rotation=(11, 15, 20), scale=(2, 2, 2))
    targets = _materials_on([root])
    matrix = cmds.xform(root, query=True, matrix=True, worldSpace=True)
    shapes = cmds.listRelatives(root, allDescendents=True, type="mesh", fullPath=True)
    points = {s: [(p.x, p.y, p.z) for p in _mesh(s).getPoints()] for s in shapes}
    roots = set(cmds.ls(assemblies=True))
    before_uvs = {s: tuple(list(v) for v in _mesh(s).getUVs()) for s in shapes}
    for name in MATERIALS:
        assert not cmds.listConnections(targets[name][0][1] + ".base_color", source=True, destination=False)
    repair(root, baked)
    assert set(cmds.ls(assemblies=True)) == roots
    assert cmds.xform(root, query=True, matrix=True, worldSpace=True) == matrix
    for shape in shapes:
        delta = max(math.dist((a.x, a.y, a.z), b) for a, b in zip(_mesh(shape).getPoints(), points[shape]))
        assert delta < 1e-5, (shape, delta)
    for name in MATERIALS:
        shape, shader = targets[name][0]
        color = cmds.listConnections(shader + ".base_color", source=True, destination=False)[0]
        assert cmds.nodeType(color) == "file"
        expected = "Procedural_Dirt_Soil" if name.startswith("Procedural") else "Material_002_Stem"
        assert expected in cmds.getAttr(color + ".fileTextureName"), cmds.getAttr(color + ".fileTextureName")
        assert Path(cmds.getAttr(color + ".fileTextureName")).is_file()
        bump = cmds.listConnections(shader + ".bump_input", source=True, destination=False)[0]
        assert cmds.nodeType(bump) == "RedshiftBumpMap"
        u, v = _mesh(shape).getUVs()
        assert len(set(zip(u, v))) > 10, "Baked atlas UVs must survive cleanup"
        assert min(u) >= -1e-5 and max(u) <= 1.00001
        assert min(v) >= -1e-5 and max(v) <= 1.00001
    changed = {targets[n][0][0] for n in MATERIALS}
    for shape in set(shapes) - changed:
        assert tuple(list(v) for v in _mesh(shape).getUVs()) == before_uvs[shape]
    cmds.undo()
    for name in MATERIALS:
        shape, shader = targets[name][0]
        assert not cmds.listConnections(shader + ".base_color", source=True, destination=False)
        assert tuple(list(v) for v in _mesh(shape).getUVs()) == before_uvs[shape]
    cmds.redo()
    for name in MATERIALS:
        assert cmds.listConnections(targets[name][0][1] + ".base_color", source=True, destination=False)
    print(
        "PASS: real ficus dirt/stem maps and UVs repaired; geometry, placement and other materials preserved; undo/redo works"
    )


if __name__ == "__main__":
    import maya.standalone

    maya.standalone.initialize(name="python")
    try:
        check(*sys.argv[1:])
    finally:
        maya.standalone.uninitialize()
