from pathlib import Path
import base64
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
archive_dir = root / "archive"

parts = sorted(archive_dir.glob("U_DINK_STORE_ALL_SOURCE.zip.b64.part*"))
if not parts:
    raise SystemExit("Archive parts not found.")

payload = "".join(p.read_text(encoding="utf-8").strip() for p in parts)
zip_path = root / "U_DINK_STORE_ALL_SOURCE.zip"
zip_path.write_bytes(base64.b64decode(payload))

extract_dir = root / "restored-source"
if extract_dir.exists():
    shutil.rmtree(extract_dir)
extract_dir.mkdir(exist_ok=True)

# The historical handoff archive contains multiple prototype versions. An older
# split transfer may contain a damaged local header for one entry even when the
# ZIP central directory and the other source files remain readable. Recover each
# readable member independently instead of losing the whole source tree.
skipped = []
extracted = []
with zipfile.ZipFile(zip_path, "r") as z:
    for info in z.infolist():
        relative = Path(info.filename)
        if info.is_dir():
            (extract_dir / relative).mkdir(parents=True, exist_ok=True)
            continue

        # Basic ZIP path traversal protection.
        target = (extract_dir / relative).resolve()
        if extract_dir.resolve() not in target.parents:
            skipped.append((info.filename, "unsafe path"))
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with z.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted.append(info.filename)
        except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
            target.unlink(missing_ok=True)
            skipped.append((info.filename, str(exc)))

index_files = list(extract_dir.rglob("index.html"))
if not index_files:
    details = "\n".join(f"- {name}: {reason}" for name, reason in skipped[:20])
    raise SystemExit(f"Archive recovery produced no index.html. Skipped entries:\n{details}")

print(f"Restored archive: {zip_path}")
print(f"Extracted readable files: {len(extracted)}")
print(f"Recovered index files: {len(index_files)}")
for path in index_files:
    print(f"- {path.relative_to(extract_dir)}")
if skipped:
    print(f"Skipped damaged/unreadable entries: {len(skipped)}")
    for name, reason in skipped:
        print(f"- {name}: {reason}")
print(f"Extracted source: {extract_dir}")
