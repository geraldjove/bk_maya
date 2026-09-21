"""Repair the imported STAEDTLER pencil's invalid IORs and missing steel.

In Maya's Python Script Editor:
    from bk_maya.scripts.repair_pencil import repair
    repair()
"""

import importlib
from pathlib import Path

from maya import cmds

from ..core import redshift
from ..core.prefs import prefs
from .repair_ficus import _mesh


def repair(root="BK_STAEDTLER_Pencil", usd_path=None):
    """Repair only this pencil, keeping placement and a single Undo step."""
    if not cmds.objExists(root):
        raise RuntimeError(f"Pencil group not found: {root}")
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Maya Undo before running the material repair.")
    importlib.reload(redshift)  # Also works in Maya sessions opened before the fix.
    redshift.ensure_available()
    shapes = cmds.listRelatives(root, allDescendents=True, type="mesh", fullPath=True) or []
    groups = set(cmds.listConnections(shapes, type="shadingEngine") or []) if shapes else set()
    shaders = set()
    for group in groups:
        shaders.update(cmds.listConnections(group + ".surfaceShader", source=True, destination=False) or [])
    shaders = sorted(s for s in shaders if cmds.nodeType(s) == "RedshiftStandardMaterial")
    missing = [s for s in shapes if "initialShadingGroup" in (cmds.listConnections(s, type="shadingEngine") or [])]
    if usd_path is None:
        directory = Path(prefs.global_dir_resolved()) / "models/staedtler-pencil_6ca9eaaa-27cf-4ae6-9fd7-60a7c5dc8e76"
        usd_path = directory / "staedtler-pencil_2K_6ca9eaaa-27cf-4ae6-9fd7-60a7c5dc8e76.redshift-baked-v2.usd"
    if missing and not Path(usd_path).is_file():
        raise RuntimeError(f"Updated pencil export not found: {usd_path}")
    selection = cmds.ls(selection=True, long=True) or []
    before = set(cmds.ls(long=True))
    before_roots = set(cmds.ls(assemblies=True, long=True))
    before_groups = set(cmds.ls(type="shadingEngine"))
    chunk = "Repair Blendkit pencil materials"
    cmds.undoInfo(openChunk=True, chunkName=chunk)
    succeeded = False
    fixed = []
    try:
        keep = set()
        if missing:
            cmds.loadPlugin("mayaUsdPlugin", quiet=True)
            cmds.mayaUSDImport(
                file=str(usd_path),
                readAnimData=False,
                shadingMode=[("useRegistry", "UsdPreviewSurface")],
                preferredMaterial="standardSurface",
                importInstances=True,
            )
            new_roots = list(set(cmds.ls(assemblies=True, long=True)) - before_roots)
            redshift.convert(sorted(set(cmds.ls(type="shadingEngine")) - before_groups))
            sources = cmds.listRelatives(new_roots, allDescendents=True, type="mesh", fullPath=True) or []
            pairs = []
            for target in missing:
                # The bake copies the mesh datablock; its object parent keeps
                # the stable Blender name while the two mesh nodes may change.
                matches = [s for s in sources if s.rsplit("|", 3)[-3] == target.rsplit("|", 3)[-3]]
                if len(matches) != 1:
                    raise RuntimeError(f"Cannot identify a replacement material for {target}")
                source = matches[0]
                source_groups = cmds.listConnections(source, type="shadingEngine") or []
                if len(source_groups) != 1 or source_groups[0] in before_groups:
                    raise RuntimeError(f"Replacement material is missing for {target}")
                group = source_groups[0]
                shader = cmds.listConnections(group + ".surfaceShader", source=True, destination=False)[0]
                if cmds.nodeType(shader) != "RedshiftStandardMaterial":
                    raise RuntimeError(f"Replacement is not a Redshift material: {shader}")
                a, b = _mesh(target), _mesh(source)
                if (
                    cmds.listConnections(target + ".inMesh", source=True, destination=False)
                    or a.numVertices != b.numVertices
                    or any(list(x) != list(y) for x, y in zip(a.getVertices(), b.getVertices()))
                ):
                    raise RuntimeError(f"Mesh topology/history changed: {target}. Re-import the pencil instead.")
                pairs.append((target, source, group, shader))
            for target, source, group, shader in pairs:
                cmds.polyTransfer(
                    target,
                    alternateObject=source,
                    uvSets=True,
                    vertices=False,
                    vertexColor=False,
                    constructionHistory=False,
                )
                cmds.polyUVSet(target, currentUVSet=True, uvSet="st")
                cmds.sets(target, edit=True, forceElement=group)
                index = next(
                    i
                    for i in cmds.getAttr(target + ".uvSet", multiIndices=True)
                    if cmds.getAttr(f"{target}.uvSet[{i}].uvSetName") == "st"
                )
                for texture in cmds.ls(cmds.listHistory(shader) or [], type="file") or []:
                    for uv_set in cmds.uvLink(query=True, texture=texture) or []:
                        cmds.uvLink(b=True, texture=texture, uvSet=uv_set)
                    cmds.uvLink(make=True, texture=texture, uvSet=f"{target}.uvSet[{index}].uvSetName")
                keep.add(group)
                keep.update(cmds.ls(cmds.listHistory(shader, pruneDagObjects=True) or [], long=True) or [])
                fixed.append(shader)
            cmds.delete(sorted(set(cmds.ls(long=True)) - before - keep))
        fixed.extend(shader for shader in shaders if redshift.repair_invalid_ior(shader))
        cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
        succeeded = True
    finally:
        cmds.undoInfo(closeChunk=True)
        if not succeeded and cmds.undoInfo(query=True, undoName=True) == chunk:
            cmds.undo()
    cmds.inViewMessage(amg=f"Blendkit: repaired {len(fixed)} pencil materials", pos="topCenter", fade=True)
    return fixed
