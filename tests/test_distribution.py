"""Catch missing vendored files/license/docs before transferring to another OS."""
import hashlib
import json
from pathlib import Path
import unittest
import tempfile
import zipfile
import importlib.util

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_vendored_sources_match_recorded_hashes(self):
        manifest = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
        for name, info in manifest["files"].items():
            with self.subTest(file=name):
                p = ROOT / "vendor/kame" / name
                self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), info["local_sha256"])

    def test_portable_build_inputs_and_documentation_exist(self):
        for name in ("LICENSE", "THIRD_PARTY.md", "UPSTREAM.json", "pyproject.toml", "setup.py", "CLAUDE.md", "README.zh-CN.md",
                     "vendor/local-fixes.patch", "native/driver.cpp", "src/gpib_macarm/api.py",
                     "docs/ARCHITECTURE.md", "docs/VALIDATION.md", "tools/make_delivery.py"):
            with self.subTest(file=name):
                self.assertTrue((ROOT / name).is_file())


    def test_release_zip_excludes_private_records_and_binaries(self):
        spec = importlib.util.spec_from_file_location("make_delivery", ROOT / "tools/make_delivery.py")
        delivery = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(delivery)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            public = ["README.md", "README.zh-CN.md", "CLAUDE.md", "docs/VALIDATION.md",
                      "src/gpib_macarm/api.py", "vendor/kame/linux-gpib/COPYING"]
            private = ["AGENTS.md", "LOCAL_INSTALL.md", "GPIB_开发测试记录.md",
                       "local-notes/CLAUDE.md", "docs/MAC_ACCEPTANCE.md", "docs/private.md",
                       "build/validation/report.json", "tools/local_helper.py",
                       "src/gpib_macarm/_driver.dylib", "src/gpib_macarm/__pycache__/api.pyc"]
            for name in public + private:
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("fixture")
            (root / "examples").mkdir()
            (root / "examples/leaked.py").symlink_to(root / "AGENTS.md")
            output = root / "dist/release.zip"
            delivery.build_source_zip(output, root)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {"GPIB-MacARM/" + p for p in public})


if __name__ == "__main__":
    unittest.main()
