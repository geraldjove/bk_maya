# Contributing

Blendkit add-on is an open-source project and we welcome contributions from the community.

## Add-on Architecture
Blendkit for Maya is made of two main parts:
- Maya plugin written in Python, which is responsible for the user interface and interaction with Maya. It draws the asset bar / search UI, does the drag-and-drop placement, asset imports (via a headless Blender that converts assets to USD), and communicates with the Client locally. Its Qt UI targets both PySide2 (Maya 2023) and PySide6 (Maya 2024+) through the vendored `qtpy` shim.
- Client written in Go, which serves as background HTTP server - a bridge between the Blendkit add-on and the Blendkit server. Its purpose is to offload the work from Maya and to provide a performant way to communicate with the Blendkit server. The Go client lives in its own repository, embedded here as the `bk_client` submodule (`bk_client/client`).

Client is compiled and its binaries are bundled into the add-on .zip file, so the user does not need to install anything else than the add-on itself.

### How it is packaged
Blendkit for Maya is packaged as a standard Maya **module**: the release zip
contains a `blendkit.mod` module file next to a `blendkit/` folder holding the
Python sources, icons, the vendored pure-Python `lib/` dependencies, and the
Client binaries for 3 platforms on 2 architectures (windows x86_64, windows
arm64, macos x86_64, macos arm64, linux x86_64, linux arm64). Users install by
unzipping **both** items into a Maya `modules` directory and restarting Maya.

Because Maya ships different Python interpreters per version, releases publish
**two** zips that differ only in their vendored `lib/`:
- `blendkit-maya-<version>-py39.zip` — Maya 2023 (Python 3.9),
- `blendkit-maya-<version>-py311.zip` — Maya 2024–2027 (Python 3.11).

When the plugin loads, it chooses the correct Client binary for the platform and
architecture and copies it to the user's Blendkit data directory, from which the
Client is later started.

### How it works
Communication between Add-on and Client happens in one way direction: add-on schedules Tasks via request and periodically gets updates about the progress and results of the tasks in reponses to the requests:
`Add-on -> Client -> Server`

1. add-on checks whether the Client is running. If it is not, it starts the bundled Client binary (`client/vX.Y.Z/blenderkit-client-<platform>-<architecture>`, copied into the user's Blendkit data directory on first run),
2. add-on periodically asks for results with GET request and Client responds to the request,

3. if needed add-on sends requests (identifying itself with app_id which is the PID of the running Maya instance) for search, download asset, get notifications, download thumbnails etc. to the Client
4. Client receives the request for work, saves it into `var Tasks map[int]map[string]*Task` and ASAP responds by OK to not block the add-on,
5. Client starts the work in goroutine, or makes request to Blendkit server, or combination of both,
6. When work is done, or response comes from Blendkit server, Client updates the results into `var Tasks map[int]map[string]*Task`.
7. next time when add-on periodically asks for results of the Tasks, Client sends the results as response.

Communication between Client and Server currently happens in one way also Client -> Server (Client makes requests to Server).

## Development

### Logging

Do not use `print()` statements in the code, use logging instead.
In the beginning of the file, there is a logger setup, if it is not already there, add it:
```python
import logging

log = logging.getLogger(__name__)
```

Then instead of `print()` use `log`:
```python
log.debug("Some minor stuff happened")
log.info("Something expected has happened")
log.warning("Something unexpected has happened")
log.error("Something went very wrong")
```

If you have an exception which you can log, use `log.exception()`, e.g.:
```python
except Exception:
    log.exception("Something went wrong and you will see full traceback below")
```

### Codestyle

We use `ruff` for lint and formatting of Python code, `pydoclint` for docstring
consistency and `bandit` for security checks. The Go client is formatted and
tested in its own repository (the `bk_client` submodule), not here. The exact
tool versions used by CI are pinned in `pyproject.toml` under
`[dependency-groups].dev`.

Install the dev tools into your active environment:
```
pip install -e .
pip install "ruff>=0.15.6" "pydoclint>=0.8.3" "bandit>=1.9.4" pre-commit
pre-commit install
```

Before committing, run the same checks CI runs:
```
ruff check .
ruff format .
pydoclint .
bandit -c _bandit.yaml -ll -r .
```

Pull requests will fail in CI if any of these report errors.

### Building the add-on

Use `bk_maya/dev.py` from the repo root to build the add-on. The script vendors
the pure-Python `lib/` dependencies, assembles the module under
`out/stage/blendkit` (skipping anything not needed in the shipped add-on) and
produces a versioned zip such as `out/blendkit-maya-<version>.zip`.

To build run:
```
python bk_maya/dev.py build
```

Pass `--python {current,3.9,3.11,both}` to control which Maya interpreter the
vendored `lib/` targets; `both` emits the `-py39` and `-py311` zips that are
shipped in releases.

#### Development build: build for quick testing

`bk_maya/dev.py` accepts `--install-at` to copy the built `blendkit/` module and
its `blendkit.mod` directly into a Maya `modules` directory, so the add-on is
ready to load on the next Maya start. The flag can be passed multiple times to
install into several targets at once.

```
python bk_maya/dev.py build --install-at /path/to/maya/modules
```

`--clean-dir` can be used to wipe a stale client binaries directory (required
when you change the Go client, otherwise the cached binary is not overwritten):

```
python bk_maya/dev.py build --install-at /path/to/maya/modules --clean-dir ~/blenderkit_data/client/bin
```

## Releasing

Before release bump `BASE_VERSION` (`major.minor`) in `bk_maya/_version.py` —
the timestamped patch and channel are generated automatically at build time.
The Go client version is managed in its own repository (the `bk_client`
submodule, `bk_client/client/VERSION`) — releases pick up the newest client
binaries available there automatically. Make sure the bump is merged into
`main`.

Releases run through `python bk_maya/dev.py release`, which downloads the
*signed* `bk_client.zip` from the `bk_client` GitHub releases (or unpacks a
locally supplied bundle via `--client-build`). CI runs it with `--python both`
and publishes the `-py39` and `-py311` zips.

## Testing

This fork retains three checks that directly support Redshift material conversion:

- `tests/test_redshift_recipe.py` checks that Redshift imports select the bundled
  baking recipe and respect an explicit export-script override.
- `tests/integration/test_redshift_import.py` checks shader values, textures,
  color spaces, normals, material assignments, invalid IOR handling, renderer
  selection and cleanup after a failed conversion in Maya standalone.
- `tests/integration/test_procedural_bake.py` checks baked procedural detail,
  usable UVs and legacy Glossy-to-metal conversion in Blender.

Run from the repository root:

```powershell
python -m unittest tests.test_redshift_recipe
python bk_maya/dev.py vendor
mayapy tests/integration/test_redshift_import.py
blender --background --factory-startup --python tests/integration/test_procedural_bake.py
```

The Maya check requires MayaUSD and Redshift; set `REDSHIFT_MAYA_PLUGIN` to the
plug-in path when it is not already discoverable. Native checks use synthetic
scenes and temporary files. Do not add downloaded assets, scene-specific repair
scripts, personal paths or generated test reports to the repository.

### Pull Requests

To contribute to the project, please create a Pull Request.
PR should contain a description of the changes and the reason for the changes.
Ideally PR should be linked to an issue in the issue tracker.

PR will be reviewed by the team and if it passes the automated tests and checks, it will be merged.

#### Automated tests

We run automated checks on Pull Requests and on pushes to `main`/`master`.
The checks which must pass for a PR to be accepted are:
- `ruff check .` — lint,
- `ruff format --check .` — formatting,
- `pydoclint .` — docstring consistency,
- `bandit -c _bandit.yaml -ll -r .` — security (medium+ severity),
- Redshift export-recipe selection on Python 3.11 and 3.12,
- automated build of the add-on via `python bk_maya/dev.py build`.

Native Maya/Redshift and Blender checks run locally because they require the
installed applications. Report their results when changing material conversion.

Those CI jobs are defined in a single workflow: `.github/workflows/CI.yml`.
