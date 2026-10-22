"""Tests for routed outdated output."""
import importlib.machinery
import importlib.util
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch
from io import StringIO
from contextlib import redirect_stdout

SOURCE = Path(__file__).resolve().parents[1] / "cmd" / "brew-intel-bottle"
loader = importlib.machinery.SourceFileLoader("intel_bottle_outdated", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
loader.exec_module(mod)


class OutdatedTests(unittest.TestCase):
    def test_unmodified_native_command(self):
        with patch.object(mod, "passthrough", return_value=0) as native:
            self.assertEqual(mod.outdated_display(["--json=v2"]), 0)
            native.assert_called_once_with(["outdated", "--json=v2"])

    def test_sort_and_verbose(self):
        sample = {"formulae": [
            {"name": "zlib", "installed_versions": ["1.0"], "current_version": "2.0"},
            {"name": "aria2", "installed_versions": ["1.0"], "current_version": "1.1"}],
            "casks": []}
        with patch.object(mod.subprocess, "run") as run, redirect_stdout(StringIO()) as out:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(sample)
            self.assertEqual(mod.outdated_display(["--sort=name", "--formula"]), 0)
            self.assertEqual(out.getvalue().splitlines(), ["aria2", "zlib"])
            self.assertIn("--formula", run.call_args.args[0])

    def test_reverse(self):
        sample = {"formulae": [
            {"name": "a", "current_version": "1"},
            {"name": "z", "current_version": "2"}], "casks": []}
        with patch.object(mod.subprocess, "run") as run, redirect_stdout(StringIO()) as out:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(sample)
            self.assertEqual(mod.outdated_display(["--sort=name", "--reverse"]), 0)
            self.assertEqual(out.getvalue().splitlines(), ["z", "a"])

    def test_unknown_dates_always_last(self):
        sample = {"formulae": [
            {"name": "known", "current_version": "2"},
            {"name": "unknown", "current_version": "3"}], "casks": []}
        with patch.object(mod.subprocess, "run") as run, patch.object(
            mod, "version_first_seen", side_effect=lambda e:
                "2026-10-01T00:00:00Z" if e["name"] == "known" else None
        ), redirect_stdout(StringIO()) as out:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(sample)
            self.assertEqual(mod.outdated_display(["--sort=date", "--reverse"]), 0)
            self.assertTrue(out.getvalue().splitlines()[0].startswith("known"))
            self.assertTrue(out.getvalue().splitlines()[1].startswith("unknown"))

    def test_revision_detection(self):
        content = 'class Test < Formula\\n  version "1.2.3"\\n  revision 2\\nend'
        self.assertEqual(mod.recipe_version(content, "formula"), "1.2.3_2")
        self.assertIsNone(mod.recipe_version('url "https://host/app-1.2.3.tar.gz"', "formula"))

    def test_current_cask_version_detection(self):
        self.assertEqual(mod.recipe_version('version "4.3.2"', "cask"), "4.3.2")

    def test_bad_sort(self):
        with self.assertRaises(mod.BottleError):
            mod.outdated_display(["--sort=unknown"])

    def test_json_with_sort_rejected(self):
        with self.assertRaises(mod.BottleError):
            mod.outdated_display(["--sort=date", "--json=v2"])


if __name__ == "__main__":
    unittest.main()
