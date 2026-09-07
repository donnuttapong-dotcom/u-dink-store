from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
RESTORED = ROOT / "restored-source"

if not RESTORED.exists():
    raise SystemExit("restored-source/ not found. Run tools/restore_source.py first.")

candidates = list(RESTORED.rglob("index.html"))
if not candidates:
    raise SystemExit("No index.html found in restored source archive.")


def score(path: Path) -> tuple[int, int, str]:
    text = str(path).lower().replace("_", "-")
    points = 0
    if "v4-motion-source" in text:
        points += 10000
    elif "v4" in text and "motion" in text:
        points += 9000
    elif "v4" in text:
        points += 8000
    if "v3-original-layout-master" in text:
        points += 5000
    if "master" in text:
        points += 500
    # Prefer a fuller source folder if names tie.
    folder = path.parent
    file_count = sum(1 for p in folder.rglob("*") if p.is_file())
    return points, file_count, str(path)

selected = max(candidates, key=score)
source_dir = selected.parent

print(f"Selected current master source: {source_dir.relative_to(RESTORED)}")

# Repository handoff/infrastructure files that must remain owned by the repo.
protected_root_names = {
    ".git",
    ".github",
    ".gitignore",
    "archive",
    "docs",
    "tools",
    "versions",
    "README.md",
    "DEVELOPMENT.md",
    "HANDOFF.md",
    "PROGRAMMER_START_HERE.md",
    "STATUS.md",
}

copied = []
for item in source_dir.iterdir():
    if item.name in protected_root_names:
        continue
    target = ROOT / item.name
    if item.is_dir():
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.copytree(item, target)
    else:
        shutil.copy2(item, target)
    copied.append(item.name)

if not (ROOT / "index.html").exists():
    raise SystemExit("Promotion failed: root index.html was not created.")

print("Promoted files/directories:")
for name in sorted(copied):
    print(f"- {name}")
