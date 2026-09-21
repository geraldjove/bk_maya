"""Convert newly imported USD Preview Surface materials to Redshift."""

from __future__ import annotations

from maya import cmds

from .prefs import prefs

# Maya's USD reader already handles texture paths and UVs.
# Reuse its file/placement nodes instead of rebuilding that network.
_INPUTS = {
    "base": "base_color_weight",
    "baseColor": "base_color",
    "diffuseRoughness": "diffuse_roughness",
    "metalness": "metalness",
    "specular": "refl_weight",
    "specularColor": "refl_color",
    "specularRoughness": "refl_roughness",
    "specularIOR": "refl_ior",
    "specularAnisotropy": "refl_aniso",
    "specularRotation": "refl_aniso_rotation",
    "transmission": "refr_weight",
    "transmissionColor": "refr_color",
    "transmissionExtraRoughness": "refr_roughness",
    "thinWalled": "refr_thin_walled",
    "coat": "coat_weight",
    "coatColor": "coat_color",
    "coatRoughness": "coat_roughness",
    "coatIOR": "coat_ior",
    "emission": "emission_weight",
    "emissionColor": "emission_color",
    "opacity": "opacity_color",
}


def is_requested() -> bool:
    """Follow the material preference, detecting the active renderer in Auto."""
    mode = prefs.material_target
    return mode == "redshift" or (mode == "auto" and cmds.getAttr("defaultRenderGlobals.currentRenderer") == "redshift")


def ensure_available() -> None:
    """Fail before importing geometry if the requested renderer is unavailable."""
    try:
        if not cmds.pluginInfo("redshift4maya", query=True, loaded=True):
            cmds.loadPlugin("redshift4maya", quiet=True)
    except RuntimeError as exc:
        raise RuntimeError(
            "Redshift materials require the redshift4maya plug-in. Enable it in "
            "Plug-in Manager, or choose Maya in Blendkit > Settings > Files > Materials."
        ) from exc


def _raw_source(plug: str, textures: dict[str, str]) -> str:
    """Use Raw for data maps without changing a file also used for color."""
    node, attr = plug.split(".", 1)
    if cmds.nodeType(node) != "file" or attr == "outAlpha":
        return plug
    if cmds.getAttr(node + ".colorSpace").lower().endswith("raw"):
        return plug
    if node not in textures:
        textures[node] = cmds.duplicate(node, inputConnections=True, name=node + "_Raw")[0]
        spaces = cmds.colorManagementPrefs(query=True, inputSpaceNames=True) or []
        raw = next((space for space in spaces if space.lower().endswith("raw")), "Raw")
        cmds.setAttr(textures[node] + ".colorSpace", raw, type="string")
        cmds.setAttr(textures[node] + ".ignoreColorSpaceFileRules", True)
    return textures[node] + "." + attr


def _copy_input(source: str, target: str, raw_textures: dict[str, str] | None = None) -> None:
    """Copy a value and its incoming connection, including individual channels."""
    incoming = cmds.connectionInfo(source, sourceFromDestination=True)
    if incoming:
        if raw_textures is not None:
            incoming = _raw_source(incoming, raw_textures)
        cmds.connectAttr(incoming, target, force=True)
        return
    value = cmds.getAttr(source)
    source_node, source_attr = source.split(".", 1)
    children = cmds.attributeQuery(source_attr, node=source_node, listChildren=True) or []
    if children:
        cmds.setAttr(target, *value[0], type=cmds.getAttr(target, type=True))
        target_node, target_attr = target.split(".", 1)
        target_children = cmds.attributeQuery(target_attr, node=target_node, listChildren=True) or []
        for child, target_child in zip(children, target_children):
            _copy_input(f"{source_node}.{child}", f"{target_node}.{target_child}", raw_textures)
    else:
        cmds.setAttr(target, value)


def _copy_normal(source: str, target: str, created: list[str], raw_textures: dict[str, str]) -> None:
    """Translate USD reader bump2d/file normal maps to a Redshift bump node."""
    incoming = cmds.connectionInfo(source, sourceFromDestination=True)
    if not incoming:
        return
    node = incoming.split(".", 1)[0]
    kind = cmds.nodeType(node)
    if kind not in ("bump2d", "file"):
        raise ValueError(f"unsupported normal node {kind}: {node}")
    bump = cmds.shadingNode("RedshiftBumpMap", asUtility=True, name=node + "_RS")
    created.append(bump)
    mode = cmds.getAttr(node + ".bumpInterp") if kind == "bump2d" else 1
    cmds.setAttr(bump + ".inputType", mode)
    # Direct USD normal inputs are signed vectors (the file node already
    # applies USD's scale/bias). bump2d inputs use encoded 0..1 normal maps.
    cmds.setAttr(bump + ".unbiasedNormalMap", kind == "file")
    if kind == "bump2d":
        texture = cmds.connectionInfo(node + ".bumpValue", sourceFromDestination=True)
        if mode and texture:
            texture_node = texture.split(".", 1)[0]
            if cmds.nodeType(texture_node) != "file":
                raise ValueError(f"unsupported normal texture: {texture_node}")
            cmds.connectAttr(_raw_source(texture_node + ".outColor", raw_textures), bump + ".input")
        else:
            for channel in "RGB":
                _copy_input(node + ".bumpValue", bump + ".input" + channel, raw_textures)
        _copy_input(node + ".bumpDepth", bump + ".scale")
    else:
        cmds.connectAttr(_raw_source(incoming, raw_textures), bump + ".input")
    cmds.connectAttr(bump + ".out", target)


def repair_invalid_ior(shader: str) -> bool:
    """Replace nonpositive legacy IOR constants with Redshift's default.

    Some downloaded Blender materials contain IOR=0, which turns painted
    surfaces into white reflectors. Preserve valid values and driven inputs.
    """
    plug = shader + ".refl_ior"
    if cmds.connectionInfo(plug, sourceFromDestination=True) or cmds.getAttr(plug) > 0:
        return False
    default = cmds.attributeQuery("refl_ior", node=shader, listDefault=True)[0]
    cmds.setAttr(plug, default)
    cmds.warning(f"Blendkit: replaced invalid reflection IOR on {shader} with {default}.")
    return True


def convert(shading_groups: list[str]) -> int:
    """Convert only the supplied new shading groups, preserving assignments."""
    converted: dict[str, str] = {}
    for group in shading_groups:
        source = cmds.connectionInfo(group + ".surfaceShader", sourceFromDestination=True)
        if not source:
            continue
        material = source.split(".", 1)[0]
        if cmds.nodeType(material) != "standardSurface":
            cmds.warning(f"Blendkit: keeping unsupported material {material} ({cmds.nodeType(material)}).")
            continue
        created: list[str] = []
        raw_textures: dict[str, str] = {}
        try:
            shader = converted.get(material)
            if shader is None:
                shader = cmds.shadingNode("RedshiftStandardMaterial", asShader=True, name=material + "_RS")
                created.append(shader)
                for old, new in _INPUTS.items():
                    _copy_input(
                        f"{material}.{old}",
                        f"{shader}.{new}",
                        None if old.endswith("Color") else raw_textures,
                    )
                repair_invalid_ior(shader)
                _copy_normal(material + ".normalCamera", shader + ".bump_input", created, raw_textures)
                _copy_normal(material + ".coatNormal", shader + ".coat_bump_input", created, raw_textures)
            # Keep the same shading group: whole-object and per-face assignments,
            # as well as the USD reader's displacement connection, survive.
            cmds.connectAttr(shader + ".outColor", group + ".surfaceShader", force=True)
            converted[material] = shader
        except (RuntimeError, ValueError) as exc:
            if created:
                cmds.delete(created + list(raw_textures.values()))
            cmds.warning(f"Blendkit: could not convert {material} to Redshift; keeping the original. {exc}")
    return len(converted)
