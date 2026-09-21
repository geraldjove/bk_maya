<div align="center">
  <img src="/bk_maya/data/icons/blendkit_logo.png" alt="Logo" width="100" height="100"/>
  <h3 align="center">Blendkit for Maya</h3>

  Asset search, download and drag&drop directly inside Autodesk Maya.

  ![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/blenderkit/bk_maya/total?color=blue)
  ![GitHub Downloads (all assets, latest release)](https://img.shields.io/github/downloads/blenderkit/bk_maya/latest/total?color=blue)
  [![GitHub Release](https://img.shields.io/github/v/release/blenderkit/bk_maya?color=green)](https://github.com/BlenderKit/bk_maya/releases/latest)
  [![Project license](https://img.shields.io/github/license/blenderkit/bk_maya.svg?color=orange)](LICENSE)
  </br>
  ![GitHub commit activity](https://img.shields.io/github/commit-activity/y/blenderkit/bk_maya?color=blue)
  ![GitHub branch check runs](https://img.shields.io/github/check-runs/blenderkit/bk_maya/main?color=green)

</div>


> **Status:** development fork with automatic Redshift material conversion.
> Build from source with `python bk_maya/dev.py build`. Packaged builds contain
> `blendkit.mod` and a `blendkit/` folder to install in Maya's `modules` directory.
> This fork checks [its own releases](https://github.com/geraldjove/bk_maya/releases)
> for updates, preserving the Redshift additions.

## About
This public fork adds automatic material conversion for **Maya Redshift Renderer**,
including procedural texture baking and fixes for legacy materials. It is based on
[BlenderKit/bk_maya](https://github.com/BlenderKit/bk_maya).

The Blendkit Maya plugin connects Autodesk Maya to the [Blendkit service](https://www.blendkit.com/) — search the library, drag&drop assets straight into the viewport, and re-use the same account / Full plan you already have for the Blender add-on.

It is a port of the official Blender add-on built on:

- Maya 2023–2027 (Python 3.9–3.11, PySide2/PySide6 via `qtpy`, OpenMaya 2.0)
- The shared Go `blenderkit-client` for downloads, auth and search
- A vendored `qtpy` / `requests` / `packaging` (see [bk_maya/lib](bk_maya/lib))

## Redshift materials

In **Blendkit > Settings > Files > Materials**, **Auto (active renderer)** converts
new model and material drops to Redshift Standard materials when Redshift is active.
Choose **Redshift** to always convert, or **Maya** to keep the original import behavior.
The `redshift4maya` plug-in must be installed and loadable.

Redshift conversion imports editable Maya geometry, overriding Reference / USD Stage.
It reuses the USD Preview Surface textures and UVs, uses Raw for data maps, converts normal maps,
and preserves whole-object and per-face material assignments. Existing scene materials
are unaffected. Re-import assets that were placed before enabling conversion.
Fully procedural Principled materials are automatically baked to per-object texture
atlases, with new UVs where needed. The first import takes longer; later imports reuse
a separate Redshift cache. The original `.blend` remains unchanged. Mixed image /
procedural graphs and complex shader mixes may still need manual conversion.
Legacy Glossy-only materials get a metal approximation with baked procedural detail;
view-dependent shader mixtures are not reproduced exactly. Nonpositive constant IORs
from older assets are replaced with Redshift's default to avoid white reflective paint.

To repair the dirt and stem on an existing `BK_Modular_ficus_plant` after its baked
export has been generated, run in Maya's Python Script Editor:

```python
from bk_maya.scripts.repair_ficus import repair
repair()
```

This transfers the baked UVs and maps onto the existing meshes and shaders in one
undoable operation, preserving placement. It refuses changed topology or mesh history.

For an existing `BK_STAEDTLER_Pencil`, after generating its updated Redshift export:

```python
from bk_maya.scripts.repair_pencil import repair
repair()
```

This corrects the pencil's invalid IORs and restores its missing steel material in one
undoable operation. Geometry and placement are preserved.

Validated with Maya 2026, Redshift 2026.9.0 and Blender 5.2 on Windows, including
a Redshift render of the corrected pencil. Other versions have not been validated.

Run these checks from a source checkout after `python bk_maya/dev.py vendor`:

```powershell
python -m unittest discover tests
mayapy tests/integration/test_redshift_import.py
blender --background --factory-startup --python tests/integration/test_procedural_bake.py
```

The Maya integration test requires MayaUSD and Redshift; set `REDSHIFT_MAYA_PLUGIN`
to the plug-in path if needed. The optional ficus/pencil repair tests take the original
and updated cached USD paths as arguments. They use separate standalone scenes.
Downloaded models and textures are not included in this repository.

The Redshift Blender recipe lives in `bk_maya/scripts/export_usd.py`, so it is
included in builds of this fork. Standard Maya imports continue using the client
recipe. Explicit export-script/environment overrides still take precedence.

## Repository layout
- [bk_maya/](bk_maya) — the Maya plugin (core, UI, plugins, vendored libs)
- [bk_maya/bk_proxor/](bk_maya/bk_proxor) — proxor mesh-preview submodule (`.prx` / `.prxc`)
- [bk_client/](bk_client) — Go `blenderkit-client` submodule, shared with the Blender add-on
- [tests/](tests) — pure-Python unit tests runnable without Maya

## Getting started (developers)

```powershell
# 1. clone with submodules
git clone --recursive https://github.com/geraldjove/bk_maya.git
cd bk_maya

# 2. create a venv and install dev tooling
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"  # or: pdm install / uv sync --group dev

# 3. enable pre-commit hooks (ruff + pydoclint)
pre-commit install

# 4. run the synthetic test suite
python -m unittest discover tests
```

To build a distributable bundle:

```powershell
python bk_maya/dev.py build
```

To load the plugin inside Maya, point Maya's plug-in path at `bk_maya/plugins/`
and load `maya_plugin.py` from `Windows ▸ Settings/Preferences ▸ Plug-in Manager`.

## Releases & versioning

- **Version scheme:** `major.minor.YYMMDDHHmm`, with a `-alpha` suffix on
  automated `main` builds (e.g. `0.1.2506071430-alpha`). The `major.minor`
  part is the single human-editable knob in [bk_maya/_version.py](bk_maya/_version.py)
  (`BASE_VERSION`); the timestamped patch + channel are generated at build time.
- **Where the version lives at runtime:** the build writes a generated
  `bk_maya/_build_version.py` into the package. The plugin reads it via
  [bk_maya/_version.py](bk_maya/_version.py) and surfaces it in the Plug-in
  Manager, the **Blendkit ▸ About** menu, and the Maya `.mod` module version —
  so users and admins can see exactly which build is installed.
- **Automated releases** (see [.github/workflows/release.yml](.github/workflows/release.yml)):
  - This fork publishes through the manual **Run workflow** action. Automatic pushes below apply to upstream.
  - merge to **`main`** → rolling **Alpha** prerelease,
  - push to **`master`** or the manual *Run workflow* button → **stable** release.
- **Zip contents** (`blendkit-maya-<version>-py39.zip` / `-py311.zip`): the
  version is in the filename, and the archive holds the `blendkit.mod` file next
  to the `blendkit/` module folder. Pick the zip matching your Maya's Python —
  `-py39` for Maya 2023, `-py311` for Maya 2024–2027 (they differ only in the
  vendored `lib/` dependency versions). Unzip **both** files into a Maya
  `modules` directory and restart Maya — see the bundled `INSTALL.txt`.
- **Build channels locally:**

  ```powershell
  python bk_maya/dev.py build                 # dev build  -> 0.1.<stamp>.dev style
  python bk_maya/dev.py build --channel alpha # alpha      -> 0.1.<stamp>-alpha
  python bk_maya/dev.py build --channel stable
  python bk_maya/dev.py build --version 0.1.2506071430   # explicit override
  python bk_maya/dev.py release --python both             # emit -py39 + -py311 zips
  ```

> **Client binaries (future change):** today the Go client is compiled from
> `client/` on every build. When it moves to its own repo and ships *signed*
> binaries, point the build at the downloaded folder with
> `--client-build <folder>` (or the `BLENDKIT_CLIENT_BINARIES` env-var) — see
> the comments in [bk_maya/dev.py](bk_maya/dev.py). No other packaging changes
> are needed.

## Quality

| Check        | Local                                   | CI                                            |
|--------------|-----------------------------------------|-----------------------------------------------|
| Lint         | `ruff check .`                          | `.github/workflows/lint.yml` → **Ruff**       |
| Format       | `ruff format --check .`                 | `.github/workflows/lint.yml` → **Ruff**       |
| Docstrings   | `pydoclint .`                           | `.github/workflows/lint.yml` → **Pydoclint**  |
| Security     | `bandit -c _bandit.yaml -r .`           | `.github/workflows/lint.yml` → **Bandit**     |
| Unit tests   | `python -m unittest discover tests`     | `.github/workflows/PR.yml` → **Maya-Port-Unit-Tests** |
| Go client    | `go test ./client/...`                  | `.github/workflows/PR.yml` → **Client-Unit-Tests** |

All checks are also wired up as a [pre-commit](https://pre-commit.com) hook — see [.pre-commit-config.yaml](.pre-commit-config.yaml).

## How to contribute
- Share the word about Blendkit with your friends and colleagues, or on social media.
- [Become a Creator](https://www.blendkit.com/become-creator/) and upload your assets to the Blendkit Free or Full Plan database.
- Report a bug or request a feature in the [issue tracker](https://github.com/BlenderKit/bk_maya/issues).
- Contribute code — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License
[GPL-3.0](LICENSE). Same license as the upstream Blender add-on.
