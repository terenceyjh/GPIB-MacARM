"""Catch missing vendored files/license/docs before transferring to another OS."""
import hashlib
import json
from pathlib import Path
import unittest

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
                     "docs/ARCHITECTURE.md", "docs/MAC_ACCEPTANCE.md", "docs/VALIDATION.md"):
            with self.subTest(file=name):
                self.assertTrue((ROOT / name).is_file())


if __name__ == "__main__":
    unittest.main()
