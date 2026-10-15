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
        for args in (["list"], ["info", "llvm"], ["--version"], ["upgrade"]):
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

    def test_revision_is_part_of_bottle_version(self):
        self.assertEqual(module.stable_version({"name": "aria2", "versions": {"stable": "1.37.0"}, "revision": 3}), "1.37.0_3")
        self.assertEqual(module.stable_version({"name": "protobuf", "versions": {"stable": "36.2"}, "revision": 0}), "36.2")

    def test_installed_dependency_with_different_version_is_preserved(self):
        def info(name):
            return {"name": name, "versions": {"stable": "3.5.9" if name == "openssl@3" else "1.37.0"},
                    "revision": 3 if name == "aria2" else 0, "bottle": {}}
        with (
            patch.object(module, "dependencies", return_value=["openssl@3"]),
            patch.object(module, "brew", return_value="/usr/local/Cellar"),
            patch.object(module, "formula_infos", side_effect=lambda names: {n: info(n) for n in names}),
            patch.object(module, "all_installed_versions", return_value={"openssl@3": ["3.6.5"], "aria2": ["1.37.0_2"]}),
        ):
            catalog = module.ReleaseCatalog("sequoia")
            with patch.object(catalog, "find", return_value=None):
                plan = module.installation_plan(["aria2"], "sequoia", catalog)
            self.assertEqual([(x.name, x.version, x.source) for x in plan], [
                ("openssl@3", "3.6.5", "installed"),
                ("aria2", "1.37.0_3", "missing"),
            ])

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
            patch.object(module, "formula_infos", side_effect=lambda names: {n: formula(n) for n in names}),
            patch.object(module, "all_installed_versions", return_value={}),
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
            patch.object(module, "show_cloud_jobs", return_value=(plan, False)),
            patch.object(module, "dependencies", return_value=[]),
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


    def test_bulk_formula_metadata(self):
        with patch.object(module, "brew", return_value=json.dumps({
            "formulae": [{"name": "aria2", "versions": {"stable": "1.37.0"}},
                         {"name": "openssl@3", "versions": {"stable": "3.5.9"}}]
        })) as native:
            info = module.formula_infos(["aria2", "openssl@3"])
            self.assertEqual(sorted(info), ["aria2", "openssl@3"])
            native.assert_called_once_with("info", "--json=v2", "--formula",
                                           "aria2", "openssl@3")

    def test_cloud_job_exact_version_matching(self):
        current = module.CloudJob("aria2", "1.37.0_3", "in_progress", None,
                                  "https://example.test/job", 123, "in_progress")
        other = module.CloudJob("aria2", "1.37.0_2", "in_progress", None,
                                "https://example.test/old", 122, "in_progress")
        catalog = module.WorkflowCatalog()
        catalog._jobs = [other, current]
        self.assertIs(catalog.match("aria2", "1.37.0_3")[0], current)
        self.assertIs(catalog.match("aria2", "1.37.0_4")[0], None)

    def test_legacy_cloud_job_never_claims_exact_match(self):
        old = module.CloudJob("aria2", None, "in_progress", None,
                              "https://example.test/old", 122, "in_progress")
        catalog = module.WorkflowCatalog()
        catalog._jobs = [old]
        active, _ = catalog.match("aria2", "1.37.0_3")
        self.assertIs(active, old)
        self.assertIsNone(active.version)

    def test_completed_cloud_failure_can_be_retried(self):
        old = module.CloudJob("aria2", "1.37.0_3", "completed", "failure",
                              "https://example.test/old", 122, "completed")
        catalog = module.WorkflowCatalog()
        catalog._jobs = [old]
        self.assertEqual(catalog.match("aria2", "1.37.0_3"), (None, old))

    def test_workflow_run_carries_versions_in_names(self):
        runs = {"workflow_runs": [{
            "id": 123, "status": "queued",
            "display_title": "Intel Bottles [aria2,llvm] versions=[aria2=1.37.0_3,llvm=23.1.3_1]",
            "html_url": "https://example.test/run",
        }]}
        def respond(path):
            if path.endswith("runs?per_page=100"):
                return runs
            return {"jobs": [{"name": "prepare", "status": "in_progress"}]}
        with patch.object(module, "github_api", side_effect=respond):
            catalog = module.WorkflowCatalog()
            active, _ = catalog.match("aria2", "1.37.0_3")
            self.assertEqual((active.name, active.version, active.status),
                             ("aria2", "1.37.0_3", "queued"))

    def test_cloud_dependency_build_coalescing(self):
        plan = [module.Planned("cares", "1", "missing"),
                module.Planned("openssl@3", "3.5.9", "missing"),
                module.Planned("aria2", "1.37.0_3", "missing")]
        with patch.object(module, "dependencies", return_value=["cares", "openssl@3"]):
            jobs = module.build_candidates(plan, ["aria2"])
        self.assertEqual([job.name for job in jobs], ["aria2"])

    def test_cloud_dependency_only_build(self):
        plan = [module.Planned("cares", "1", "missing"),
                module.Planned("aria2", "1.37.0_3", "release")]
        jobs = module.build_candidates(plan, ["aria2"])
        self.assertEqual([job.name for job in jobs], ["cares"])

    def test_cloud_multiple_roots_deduplicate_shared_dependency(self):
        plan = [module.Planned("common", "1", "missing"),
                module.Planned("root-a", "2", "missing"),
                module.Planned("root-b", "3", "missing")]
        with patch.object(module, "dependencies", return_value=["common"]):
            jobs = module.build_candidates(plan, ["root-a", "root-b"])
        self.assertEqual([job.name for job in jobs], ["root-a", "root-b"])

    def test_cloud_dispatch_always_pins_versions(self):
        items = [module.Planned("aria2", "1.37.0_3", "missing"),
                 module.Planned("openssl@3", "3.5.9", "missing")]
        with patch.object(module.shutil, "which", return_value="/usr/local/bin/gh"), \
             patch.object(module.subprocess, "run") as call:
            call.return_value.returncode = 0
            self.assertEqual(module.dispatch_build(items), 0)
            cmd = call.call_args.args[0]
            self.assertIn("versions=aria2=1.37.0_3,openssl@3=3.5.9", cmd)
            self.assertIn("formulae=aria2,openssl@3", cmd)

    def test_build_avoids_repeated_active_job(self):
        with patch.object(module, "formula_info",
                          return_value={"name": "aria2", "versions": {"stable": "1.37.0"}, "revision": 3}), \
             patch.object(module, "show_cloud_jobs", return_value=([], True)), \
             patch.object(module, "dispatch_build") as dispatch:
            self.assertEqual(module.trigger_build(["aria2"]), 0)
            dispatch.assert_not_called()


    def test_alias_and_explicit_help_are_combined(self):
        from contextlib import redirect_stdout
        from io import StringIO

        # Direct extension, aliased brew, and legacy proxy should all
        # reveal the extensions AND forwarded native Homebrew commands.
        for args in ([], ["--help"], ["-h"], ["help"],
                     ["intel-bottle", "--help"], ["intel-bottle", "-h"],
                     ["--proxy", "--help"], ["--proxy", "help"],
                     ["--proxy", "intel-bottle", "--help"]):
            with self.subTest(args=args), patch.object(module, "passthrough") as native:
                out = StringIO()
                with redirect_stdout(out):
                    self.assertEqual(module.main(args), 0)
                help_text = out.getvalue()
                for expected in ("brew intel-bottle", "jobs [--all]",
                                 "status FORMULA", "build [--force]",
                                 "Original Homebrew commands", "info [FORMULA|CASK...]",
                                 "upgrade [FORMULA|CASK...]", "command brew --help"):
                    self.assertIn(expected, help_text)
                native.assert_not_called()

    def test_alias_forwards_native_commands_and_enables_jobs(self):
        for args in (["info", "aria2"], ["--version"], ["outdated"],
                     ["list"], ["upgrade"], ["doctor"]):
            with self.subTest(args=args), patch.object(module, "passthrough", return_value=17) as native:
                self.assertEqual(module.main(args), 17)
                native.assert_called_once_with(args)
        # Both current and old aliased shells accept the extension.
        with patch.object(module, "parse_jobs_options", return_value=0) as jobs:
            for args in (["jobs", "aria2"], ["intel-bottle", "jobs", "--all"],
                         ["--proxy", "jobs", "aria2"],
                         ["--proxy", "intel-bottle", "jobs", "--all"]):
                with self.subTest(args=args):
                    self.assertEqual(module.main(args), 0)
            self.assertEqual(jobs.call_count, 4)

    def test_jobs_filtered_active_vs_all(self):
        from contextlib import redirect_stdout
        from io import StringIO
        queued = module.CloudJob("aria2", "1.37.0_3", "in_progress", None,
                                 "https://example.test/active", 301, "in_progress")
        failed = module.CloudJob("aria2", "1.37.0_2", "completed", "failure",
                                 "https://example.test/failed", 299, "completed")
        other = module.CloudJob("llvm", None, "queued", None,
                                "https://example.test/llvm", 300, "queued")
        with patch.object(module.WorkflowCatalog, "all", return_value=[queued, failed, other]):
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(module.parse_jobs_options(["aria2"]), 0)
            self.assertIn("aria2 1.37.0_3: in_progress", out.getvalue())
            self.assertNotIn("1.37.0_2", out.getvalue())
            self.assertNotIn("llvm", out.getvalue())

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(module.parse_jobs_options(["--all", "aria2"]), 0)
            self.assertIn("aria2 1.37.0_2: failure", out.getvalue())
            self.assertIn("https://example.test/failed", out.getvalue())
            self.assertNotIn("llvm", out.getvalue())

            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(module.parse_jobs_options([]), 0)
            self.assertIn("version unverified", out.getvalue())
            self.assertIn("llvm", out.getvalue())

    def test_jobs_options_validation_and_help(self):
        for args in (["--unknown"], ["aria2", "llvm"], ["--all", "-x"]):
            with self.subTest(args=args), self.assertRaises(module.BottleError):
                module.parse_jobs_options(args)
        from contextlib import redirect_stdout
        from io import StringIO
        out = StringIO()
        with redirect_stdout(out):
            self.assertEqual(module.parse_jobs_options(["--help"]), 0)
        self.assertIn("jobs [--all] [FORMULA]", out.getvalue())

    def test_job_catalog_excludes_coordinators_and_optional_history(self):
        run = lambda i, status: {"id": i, "status": status,
                                 "display_title": "old workflow",
                                 "html_url": f"https://example.test/{i}"}
        def responder(path):
            if path.endswith("/runs?per_page=100"):
                return {"workflow_runs": [run(9, "in_progress"), run(8, "completed")]}
            if path.endswith("/9/jobs?per_page=100"):
                return {"jobs": [
                    {"name": "prepare", "status": "completed", "conclusion": "success"},
                    {"name": "aria2", "status": "in_progress", "conclusion": None},
                ]}
            if path.endswith("/8/jobs?per_page=100"):
                return {"jobs": [
                    {"name": "publish", "status": "completed", "conclusion": "success"},
                    {"name": "protobuf", "status": "completed", "conclusion": "failure"},
                ]}
            raise AssertionError(path)
        with patch.object(module, "github_api", side_effect=responder) as api:
            self.assertEqual([j.name for j in module.WorkflowCatalog(history_limit=0).all()], ["aria2"])
            self.assertEqual([j.name for j in module.WorkflowCatalog(history_limit=20).all()],
                             ["aria2", "protobuf"])
            self.assertEqual(api.call_count, 5)


if __name__ == "__main__":
    unittest.main()