"""Bundle a pip-installable sdist with end-user guides; never sweep in private files."""
import argparse
import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT_FILES = {
    ".gitattributes", ".gitignore", "LICENSE", "THIRD_PARTY.md", "UPSTREAM.json",
    "README.md", "README.zh-CN.md", "CLAUDE.md", "CHANGELOG.md",
    "pyproject.toml", "setup.py", "MANIFEST.in",
}
PUBLIC_DOCS = {"docs/ARCHITECTURE.md", "docs/VALIDATION.md", "docs/BENCH_TESTS.md"}
RELEASE_GUIDES = {"release/README.md", "release/README.zh-CN.md", "release/CLAUDE.md"}
PUBLIC_TOOLS = {
    "tools/hardware_smoke.py", "tools/keithley_2400_iv.py",
    "tools/keithley_2400_acquire.py",
    "tools/keithley_2400_check.py",
    "tools/bus_smoke.py",
    "tools/bench_acceptance.py",
    "tools/sr830_recovery_check.py", "tools/make_delivery.py",
    "tools/test_native.sh", "tools/vendor_patch.py",
}
SOURCE_TREES = {
    "src/gpib_macarm": {".py", ".typed"},
    "native": {".cpp", ".h"},
    "vendor": {".c", ".cpp", ".h", ".patch"},
    "examples": {".py"},
    "tests": {".py", ".c", ".cpp"},
}
VENDOR_NOTICES = {"README", "AUTHORS", "COPYING"}


def public_source_files(root=ROOT):
    """Return only documented public inputs, ignoring unknown files and symlinks."""
    root = Path(root)
    result = set()
    for name in PUBLIC_ROOT_FILES | PUBLIC_DOCS | PUBLIC_TOOLS | RELEASE_GUIDES:
        p = root / name
        if p.is_file() and not p.is_symlink():
            result.add(p)
    for folder, suffixes in SOURCE_TREES.items():
        for p in (root / folder).rglob("*"):
            rel = p.relative_to(root)
            if (not p.is_file() or p.is_symlink()
                    or any(part.startswith(".") or part == "__pycache__" for part in rel.parts)
                    or any((root / parent).is_symlink() for parent in rel.parents)):
                continue
            if p.suffix in suffixes or (folder == "vendor" and p.name in VENDOR_NOTICES):
                result.add(p)
    return sorted(result)


def build_source_zip(output, root=ROOT):
    root, output = Path(root), Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    files = public_source_files(root)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in files:
            archive.write(p, "GPIB-MacARM/" + p.relative_to(root).as_posix())
    return len(files)


def project_version(root=ROOT):
    return re.search(r'^version = "([^"]+)"',
                     (Path(root) / "pyproject.toml").read_text(), re.MULTILINE).group(1)


def build_release_zip(output, sdist, root=ROOT):
    """Put the unchanged sdist and dedicated guides together in one folder."""
    root, output, sdist = Path(root), Path(output), Path(sdist)
    version = project_version(root)
    if sdist.name != f"gpib_macarm-{version}.tar.gz":
        raise ValueError("The source archive filename must match the project version")
    inputs = {"README.md": root / "release/README.md",
              "README.zh-CN.md": root / "release/README.zh-CN.md",
              "CLAUDE.md": root / "release/CLAUDE.md",
              "LICENSE": root / "LICENSE", "THIRD_PARTY.md": root / "THIRD_PARTY.md",
              sdist.name: sdist}
    contents = {}
    for name, path in inputs.items():
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or unsafe release input: {path}")
        contents[name] = path.read_bytes()
    contents["SHA256SUMS.txt"] = "".join(
        hashlib.sha256(data).hexdigest() + "  " + name + "\n"
        for name, data in sorted(contents.items())).encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            archive.writestr(f"GPIB-MacARM-{version}/{name}", data)
    return len(contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true", help="Build a developer source ZIP instead")
    args = parser.parse_args()
    version = project_version()
    dest = ROOT / "dist"
    if args.source:
        output = dest / f"gpib-macarm-{version}-source.zip"
        count = build_source_zip(output)
    else:
        output = dest / f"gpib-macarm-{version}-release.zip"
        count = build_release_zip(output, dest / f"gpib_macarm-{version}.tar.gz")
    print(f"{output}: {count} files, {output.stat().st_size} bytes, "
          f"SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
