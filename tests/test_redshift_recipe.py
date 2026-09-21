"""Ensure builds select the Maya-owned Redshift recipe."""

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from bk_maya.scripts.bg_download import _find_export_usd_script


class TestRedshiftRecipe(unittest.TestCase):
    def test_redshift_recipe_and_explicit_override(self):
        recipe = Path(__file__).resolve().parents[1] / "bk_maya/scripts/export_usd.py"
        with patch.dict(os.environ, {"BLENDKIT_TOOLS_DIR": ""}):
            self.assertEqual(Path(_find_export_usd_script({"bake_procedural": True})), recipe)
            override = str(Path(__file__).resolve())
            self.assertEqual(
                _find_export_usd_script({"bake_procedural": True, "export_usd_script": override}), override
            )
