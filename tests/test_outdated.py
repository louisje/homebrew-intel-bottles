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

    def test_bad_sort(self):
        with self.assertRaises(mod.BottleError):
            mod.outdated_display(["--sort=unknown"])

    def test_json_with_sort_rejected(self):
        with self.assertRaises(mod.BottleError):
            mod.outdated_display(["--sort=date", "--json=v2"])


if __name__ == "__main__":
    unittest.main()
