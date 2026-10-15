#!/usr/bin/env python3
"""Regression tests for the transparent Homebrew external command."""
import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "cmd" / "brew-intel-bottle"
loader = importlib.machinery.SourceFileLoader("intel_bottle", str(SCRIPT))
spec = importlib.util.spec_from_loader("intel_bottle", loader)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
loader.exec_module(module)


class BottleTests(unittest.TestCase):
    def test_passthrough_preserves_native_commands(self):
        for args in (["list"], ["info", "llvm"], ["--version"], ["upgrade"], ["--help"]):
            with self.subTest(args=args), patch.object(module, "passthrough", return_value=42) as native:
                self.assertEqual(module.main(args), 42)
                native.assert_called_once_with(args)

    def test_alias_with_explicit_command(self):
        with patch.object(module, "passthrough", return_value=0) as native:
            module.main(["intel-bottle", "list"])
            native.assert_called_once_with(["list"])

    def test_formula_validation(self):
        for invalid in ("a/b", "x;touch /tmp/pwned", "../x", "-v", ""):
            with self.subTest(invalid=invalid), self.assertRaises(module.BottleError):
                module.validate_formula(invalid)
        module.validate_formula("llvm@21")

    def test_official_bottle(self):
        info = {"bottle": {"stable": {"files": {"sequoia": {"sha256": "xxx"}}}}}
        self.assertTrue(module.official_bottle(info, "sequoia"))
        self.assertFalse(module.official_bottle(info, "sonoma"))

    def test_catalog_prefers_matching_version_and_checksum(self):
        meta = {
            "protobuf": {
                "formula": {"pkg_version": "36.2"},
                "bottle": {"cellar": "any", "tags": {
                    "sequoia": {"local_filename": "protobuf--36.2.sequoia.bottle.1.tar.gz", "sha256": "abcd"}
                }},
            }
        }
        assets = [
            {"name": "protobuf--36.2.sequoia.bottle.json", "browser_download_url": "https://example.test/meta"},
            {"name": "protobuf--36.2.sequoia.bottle.1.tar.gz", "browser_download_url": "https://example.test/zip"},
        ]
        rel = {"assets": assets, "html_url": "https://github.com/example/releases/1"}
        with patch.object(module, "github_api", return_value=[rel]), patch.object(module, "read_url", return_value=json.dumps(meta).encode()):
            cat = module.ReleaseCatalog("sequoia")
            item = cat.find("protobuf", "36.2", "/usr/local/Cellar")
            self.assertIsNotNone(item)
            self.assertEqual(item.sha256, "abcd")
            self.assertIsNone(cat.find("protobuf", "37.0", "/usr/local/Cellar"))

    def test_checks_sha256_before_installing(self):
        b = module.Bottle(
            "protobuf", "36.2", "protobuf--36.2.sequoia.bottle.tar.gz",
            "0" * 64, "https://example.test/archive", "https://example.test/release", "any"
        )
        class BytesResponse:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, n): return b"tampered bottle" if not hasattr(self, "done") else b""
        def open_bytes(*args, **kwargs):
            stream = BytesResponse()
            original = stream.read
            def read(n):
                if hasattr(stream, "done"): return b""
                stream.done = True
                return b"tampered bottle"
            stream.read = read
            return stream
        with tempfile.TemporaryDirectory() as directory, patch.object(module.urllib.request, "urlopen", side_effect=open_bytes):
            with self.assertRaisesRegex(module.BottleError, "SHA256 mismatch"):
                module.download_verified(b, Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_planning_includes_dependencies_before_target(self):
        formula = lambda n: {"name": n, "versions": {"stable": "1"}, "bottle": {}}
        with (
            patch.object(module, "dependencies", return_value=["abseil"]),
            patch.object(module, "brew", return_value="/usr/local/Cellar"),
            patch.object(module, "formula_info", side_effect=formula),
            patch.object(module, "installed_versions", return_value=[]),
        ):
            catalog = module.ReleaseCatalog("sequoia")
            with patch.object(catalog, "find", return_value=None):
                plan = module.installation_plan(["protobuf"], "sequoia", catalog)
            self.assertEqual([p.name for p in plan], ["abseil", "protobuf"])
            self.assertEqual([p.source for p in plan], ["missing", "missing"])

    def test_missing_bottles_never_start_native_source_build(self):
        plan = [module.Planned("llvm", "23.1.3", "missing")]
        with (
            patch.object(module, "check_platform", return_value="sequoia"),
            patch.object(module, "installation_plan", return_value=plan),
            patch.object(module.subprocess, "call") as native,
            patch.object(module.sys.stdin, "isatty", return_value=False),
        ):
            self.assertEqual(module.install(["llvm"]), 2)
            native.assert_not_called()

    def test_dry_run_does_not_install(self):
        plan = [module.Planned("protobuf", "36.2", "official")]
        with (
            patch.object(module, "check_platform", return_value="sequoia"),
            patch.object(module, "installation_plan", return_value=plan),
            patch.object(module.subprocess, "call") as native,
        ):
            self.assertEqual(module.install(["protobuf"], dry_run=True), 0)
            native.assert_not_called()


if __name__ == "__main__":
    unittest.main()
