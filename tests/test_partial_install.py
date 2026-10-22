"""Regression tests for independent bottle installation in mixed batches."""
import importlib.machinery
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "cmd" / "brew-intel-bottle"
loader = importlib.machinery.SourceFileLoader("intel_bottle", str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
loader.exec_module(module)


class PartialInstallTests(unittest.TestCase):
    def test_independent_roots_install(self):
        plan = [
            module.Planned("a", "1", "missing"),
            module.Planned("b", "1", "official"),
            module.Planned("c", "1", "release"),
        ]
        with patch.object(module, "dependencies", return_value=[]):
            ready, blocked = module.ready_installation_plan(plan, ["a", "b", "c"])
        self.assertEqual([p.name for p in ready], ["b", "c"])
        self.assertEqual(blocked, ["a"])

    def test_dependent_root_is_blocked(self):
        plan = [
            module.Planned("a", "1", "missing"),
            module.Planned("b", "1", "official"),
            module.Planned("c", "1", "official"),
        ]
        dep = {"a": [], "b": ["a"], "c": []}
        with patch.object(module, "dependencies", side_effect=lambda name: dep[name]):
            ready, blocked = module.ready_installation_plan(plan, ["a", "b", "c"])
        self.assertEqual([p.name for p in ready], ["c"])
        self.assertEqual(blocked, ["a", "b"])

    def test_ready_dependency_is_installed_before_root(self):
        plan = [
            module.Planned("dep", "1", "official"),
            module.Planned("a", "1", "missing"),
            module.Planned("b", "1", "official"),
        ]
        dep = {"a": ["dep"], "b": ["dep"]}
        with patch.object(module, "dependencies", side_effect=lambda name: dep[name]):
            ready, blocked = module.ready_installation_plan(plan, ["a", "b"])
        self.assertEqual([p.name for p in ready], ["dep", "b"])
        self.assertEqual(blocked, ["a"])

    def test_missing_dependency_blocks_root(self):
        plan = [
            module.Planned("dep", "1", "missing"),
            module.Planned("b", "1", "official"),
        ]
        with patch.object(module, "dependencies", return_value=["dep"]):
            ready, blocked = module.ready_installation_plan(plan, ["b"])
        self.assertEqual(ready, [])
        self.assertEqual(blocked, ["b"])

    def test_no_missing_bottles_keeps_original_plan(self):
        plan = [module.Planned("dep", "1", "installed"),
                module.Planned("b", "1", "official")]
        with patch.object(module, "dependencies") as dependencies:
            ready, blocked = module.ready_installation_plan(plan, ["b"])
        self.assertEqual(ready, plan)
        self.assertEqual(blocked, [])
        dependencies.assert_not_called()


if __name__ == "__main__":
    unittest.main()
