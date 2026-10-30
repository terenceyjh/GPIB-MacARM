"""Build a portable SOURCE zip. Host binaries/caches/build trees are excluded."""
import hashlib
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "dist"
DEST.mkdir(exist_ok=True)
excluded_dirs = {"build", "dist", "artifacts", ".venv", ".git", "__pycache__"}
excluded_suffixes = {".pyc", ".o", ".so", ".dylib", ".dll", ".pyd"}
output = DEST / "gpib-macarm-0.1.0-source.zip"
files = []
for p in ROOT.rglob("*"):
    rel = p.relative_to(ROOT)
    if not p.is_file() or any(x in excluded_dirs or x.endswith(".egg-info") for x in rel.parts):
        continue
    if p.suffix in excluded_suffixes:
        continue
    files.append(p)
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for p in sorted(files):
        archive.write(p, "GPIB-MacARM/" + p.relative_to(ROOT).as_posix())
digest = hashlib.sha256(output.read_bytes()).hexdigest()
(DEST / "SHA256SUMS.txt").write_text(digest + "  " + output.name + "\n", encoding="ascii")
print(f"{output}: {len(files)} source files, {output.stat().st_size} bytes, SHA256 {digest}")
