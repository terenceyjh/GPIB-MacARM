"""Build a curated SOURCE zip; private working-directory files are never swept in."""
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
PUBLIC_DOCS = {"docs/ARCHITECTURE.md", "docs/VALIDATION.md"}
PUBLIC_TOOLS = {
    "tools/hardware_smoke.py", "tools/keithley_2400_iv.py",
    "tools/sr830_recovery_check.py", "tools/make_delivery.py",
    "tools/test_native.sh", "tools/vendor_patch.py",
}
SOURCE_TREES = {
    "src/gpib_macarm": {".py", ".typed"},
    "native": {".cpp", ".h"},
    "vendor": {".c", ".cpp", ".h", ".patch"},
    "examples": {".py"},
    "tests": {".py", ".c"},
}
VENDOR_NOTICES = {"README", "AUTHORS", "COPYING"}


def public_source_files(root=ROOT):
    """Return only documented public inputs, ignoring unknown files and symlinks."""
    root = Path(root)
    result = set()
    for name in PUBLIC_ROOT_FILES | PUBLIC_DOCS | PUBLIC_TOOLS:
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


def main():
    version = re.search(r'^version = "([^"]+)"',
                        (ROOT / "pyproject.toml").read_text(), re.MULTILINE).group(1)
    dest = ROOT / "dist"
    output = dest / f"gpib-macarm-{version}-source.zip"
    count = build_source_zip(output)
    archives = sorted([*dest.glob(f"gpib-macarm-{version}-source.zip"),
                       *dest.glob(f"gpib_macarm-{version}.tar.gz")])
    (dest / "SHA256SUMS.txt").write_text("".join(
        hashlib.sha256(p.read_bytes()).hexdigest() + "  " + p.name + "\n"
        for p in archives), encoding="ascii")
    print(f"{output}: {count} source files, {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
