from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).parent.resolve()

BUILD_DIR = ROOT / "build"
TARGET_DIR = BUILD_DIR / "roboterSteve"

print("Erstelle Deployment-Paket...")

# Build-Verzeichnis löschen
if BUILD_DIR.exists():
    shutil.rmtree(BUILD_DIR)

TARGET_DIR.mkdir(parents=True)

# Frontend bauen
print("Frontend build...")

subprocess.run(
    ["npm", "run", "build"],
    cwd=ROOT / "frontend",
    check=True,
)

# Verzeichnisse kopieren
COPY_DIRS = [
    "backend",
]

for folder in COPY_DIRS:
    src = ROOT / folder

    if src.exists():
        shutil.copytree(
            src,
            TARGET_DIR / folder,
            dirs_exist_ok=True,
        )

# Frontend dist kopieren
shutil.copytree(
    ROOT / "frontend" / "dist",
    TARGET_DIR / "frontend" / "dist",
    dirs_exist_ok=True,
)

# Dateien kopieren
COPY_FILES = [
    "config.yaml",
    "main.py",
]

for file_name in COPY_FILES:
    src = ROOT / file_name

    if src.exists():
        shutil.copy2(
            src,
            TARGET_DIR / file_name,
        )

print()
print("Deployment erstellt:")
print(TARGET_DIR)