"""Repair the two procedural materials on an already imported ficus plant.

In Maya's Python Script Editor:
    from bk_maya.scripts.repair_ficus import repair
    repair()
"""

import re
from pathlib import Path

from maya import cmds
from maya.api import OpenMaya as om

from ..core import redshift
from ..core.prefs import prefs

MATERIALS = ("Procedural_Dirt_Surface_RS", "Material_002_BsdfPrincipled_RS")


def _mesh(shape):
    selection = om.MSelectionList()
    selection.add(shape)
    return om.MFnMesh(selection.getDagPath(0))


def _materials_on(roots):
    pairs = {}
    for shape in cmds.listRelatives(roots, allDescendents=True, type="mesh", fullPath=True) or []:
        for group in cmds.listConnections(shape, type="shadingEngine") or []:
            shaders = cmds.listConnections(group + ".surfaceShader", source=True, destination=False) or []
            for shader in shaders:
                for name in MATERIALS:
                    if re.fullmatch(re.escape(name.removesuffix("_RS")) + r"\d*_RS\d*", shader):
                        pairs.setdefault(name, []).append((shape, shader))
    return pairs


def repair(root="BK_Modular_ficus_plant", usd_path=None):
    """Replace the missing maps and UVs; preserve geometry and placement.

    Refuse changed topology. All scene edits are one undoable operation.
    """
    if not cmds.objExists(root):
        raise RuntimeError(f"Plant group not found: {root}")
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError("Enable Maya Undo before running the material repair.")
    if usd_path is None:
        directory = Path(prefs.global_dir_resolved()) / "models/modular-ficus-pl_c35f0046-1e61-43c2-b4d4-04b00a05c244"
        stem = "modular-ficus-plant_2K_c35f0046-1e61-43c2-b4d4-04b00a05c244"
        usd_path = directory / (stem + ".redshift-baked-v2.usd")
        if not usd_path.is_file():
            usd_path = directory / (stem + ".redshift-baked-v1.usd")
    if not Path(usd_path).is_file():
        raise RuntimeError(f"Baked ficus export not found: {usd_path}")
    targets = _materials_on([root])
    if any(len(targets.get(name, [])) != 1 for name in MATERIALS):
        raise RuntimeError("Expected one dirt mesh and one stem mesh under the plant group.")
    redshift.ensure_available()
    cmds.loadPlugin("mayaUsdPlugin", quiet=True)
    selection = cmds.ls(selection=True, long=True) or []
    before = set(cmds.ls(long=True))
    before_roots = set(cmds.ls(assemblies=True, long=True))
    before_groups = set(cmds.ls(type="shadingEngine"))
    cmds.undoInfo(openChunk=True, chunkName="Repair Blendkit ficus materials")
    succeeded = False
    try:
        cmds.mayaUSDImport(
            file=str(usd_path),
            readAnimData=False,
            shadingMode=[("useRegistry", "UsdPreviewSurface")],
            preferredMaterial="standardSurface",
            importInstances=True,
        )
        new_roots = list(set(cmds.ls(assemblies=True, long=True)) - before_roots)
        redshift.convert(sorted(set(cmds.ls(type="shadingEngine")) - before_groups))
        sources = _materials_on(new_roots)
        # Validate every pair before touching the existing meshes/materials.
        for name in MATERIALS:
            if len(sources.get(name, [])) != 1:
                raise RuntimeError(f"Cannot identify the baked material for {name}: {sources}")
            target_shape, _ = targets[name][0]
            source_shape, _ = sources[name][0]
            if cmds.listConnections(target_shape + ".inMesh", source=True, destination=False):
                raise RuntimeError(f"{target_shape} has construction history; repair a fresh import instead.")
            a, b = _mesh(target_shape), _mesh(source_shape)
            if a.numVertices != b.numVertices or any(
                list(x) != list(y) for x, y in zip(a.getVertices(), b.getVertices())
            ):
                raise RuntimeError(f"{target_shape} topology has changed; re-import the baked plant instead.")
        for name in MATERIALS:
            target_shape, target_shader = targets[name][0]
            source_shape, source_shader = sources[name][0]
            cmds.polyTransfer(
                target_shape,
                alternateObject=source_shape,
                uvSets=True,
                vertices=False,
                vertexColor=False,
                constructionHistory=False,
            )
            cmds.polyUVSet(target_shape, currentUVSet=True, uvSet="st")
            for attr in ("base_color", "refl_roughness", "bump_input"):
                destination = target_shader + "." + attr
                incoming = cmds.connectionInfo(destination, sourceFromDestination=True)
                if incoming:
                    cmds.disconnectAttr(incoming, destination)
                redshift._copy_input(source_shader + "." + attr, destination)
            # Repoint texture UV links to the existing mesh before removing
            # the temporary import (including links inherited by Raw copies).
            index = next(
                i
                for i in cmds.getAttr(target_shape + ".uvSet", multiIndices=True)
                if cmds.getAttr(f"{target_shape}.uvSet[{i}].uvSetName") == "st"
            )
            for texture in cmds.ls(cmds.listHistory(target_shader) or [], type="file") or []:
                for uv_set in cmds.uvLink(query=True, texture=texture) or []:
                    cmds.uvLink(b=True, texture=texture, uvSet=uv_set)
                cmds.uvLink(make=True, texture=texture, uvSet=f"{target_shape}.uvSet[{index}].uvSetName")
        keep = set()
        for name in MATERIALS:
            shader = targets[name][0][1]
            keep.update(cmds.ls(cmds.listHistory(shader, pruneDagObjects=True) or [], long=True) or [])
        created = set(cmds.ls(long=True)) - before
        # Retain only the new maps now feeding the original Redshift shaders.
        cmds.delete(sorted(created - keep))
        cmds.select(selection, replace=True) if selection else cmds.select(clear=True)
        succeeded = True
    finally:
        cmds.undoInfo(closeChunk=True)
        if not succeeded and cmds.undoInfo(query=True, undoName=True) == "Repair Blendkit ficus materials":
            cmds.undo()
    cmds.inViewMessage(amg="Blendkit: repaired ficus dirt and stem materials", pos="topCenter", fade=True)
    return list(MATERIALS)
