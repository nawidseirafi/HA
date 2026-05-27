import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = BASE_DIR / "data" / "invoices" / "invoices.db"
DEFAULT_ARCHIVE = BASE_DIR / "data" / "invoices" / "archive"
DEFAULT_BACKUP = BASE_DIR / "data" / "invoices" / "archive_cleanup_backup"


@dataclass
class ArchiveCleanupResult:
    archive_files: int
    db_references: int
    unreferenced: int
    missing: int
    moved: int = 0
    backup_dir: Path = None
    unreferenced_examples: list[Path] = None
    missing_examples: list[Path] = None

    def __post_init__(self):
        if self.unreferenced_examples is None:
            self.unreferenced_examples = []
        if self.missing_examples is None:
            self.missing_examples = []


def cleanup_archive(
    database_path: Path,
    archive_dir: Path,
    backup_dir: Path,
    apply: bool = False,
) -> ArchiveCleanupResult:
    referenced = _referenced_archive_paths(database_path, archive_dir)
    archive_files = _archive_files(archive_dir)
    unreferenced = sorted(archive_files - referenced)
    missing = sorted(referenced - archive_files)

    run_backup_dir = None
    moved = 0
    if apply and unreferenced:
        run_backup_dir = backup_dir / datetime.now().strftime("%Y%m%dT%H%M%S")
        for source in unreferenced:
            relative = source.relative_to(archive_dir)
            target = run_backup_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
            moved += 1
        _remove_empty_dirs(archive_dir)

    return ArchiveCleanupResult(
        archive_files=len(archive_files),
        db_references=len(referenced),
        unreferenced=len(unreferenced),
        missing=len(missing),
        moved=moved,
        backup_dir=run_backup_dir,
        unreferenced_examples=unreferenced[:20],
        missing_examples=missing[:20],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Unreferenzierte Archivdateien finden oder in ein Backup verschieben."
    )
    parser.add_argument("--apply", action="store_true", help="Dateien wirklich in den Backup-Ordner verschieben.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Pfad zur invoices.db.")
    parser.add_argument("--archive-dir", type=Path, default=DEFAULT_ARCHIVE, help="Archiv-Ordner.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP, help="Backup-Ziel fuer verschobene Dateien.")
    args = parser.parse_args()

    database_path = _resolve(args.database)
    archive_dir = _resolve(args.archive_dir)
    backup_dir = _resolve(args.backup_dir)

    result = cleanup_archive(database_path, archive_dir, backup_dir, apply=args.apply)

    print(f"Archivdateien: {result.archive_files}")
    print(f"DB-Referenzen: {result.db_references}")
    print(f"Unreferenziert: {result.unreferenced}")
    print(f"DB-Referenzen ohne Datei: {result.missing}")

    if result.unreferenced_examples:
        print("\nBeispiele unreferenzierter Dateien:")
        for path in result.unreferenced_examples:
            print(f"- {path.relative_to(BASE_DIR)}")

    if result.missing_examples:
        print("\nBeispiele fehlender referenzierter Dateien:")
        for path in result.missing_examples:
            print(f"- {path}")

    if not args.apply:
        print("\nDry run. Mit --apply werden unreferenzierte Dateien in den Backup-Ordner verschoben.")
        return

    print(f"\nVerschoben: {result.moved}")
    print(f"Backup: {result.backup_dir}")


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path.resolve()
    return (BASE_DIR / path).resolve()


def _referenced_archive_paths(database_path: Path, archive_dir: Path) -> set[Path]:
    if not database_path.exists():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {database_path}")

    con = sqlite3.connect(database_path)
    try:
        rows = con.execute(
            """
            select archive_path
            from invoices
            where status = 'archived'
              and archive_path is not null and archive_path != ''
            """
        ).fetchall()
    finally:
        con.close()

    referenced = set()
    archive_root = archive_dir.resolve()
    for row in rows:
        path = Path(row[0]).expanduser().resolve()
        try:
            path.relative_to(archive_root)
        except ValueError:
            continue
        referenced.add(path)
    return referenced


def _archive_files(archive_dir: Path) -> set[Path]:
    if not archive_dir.exists():
        return set()
    return {
        path.resolve()
        for path in archive_dir.rglob("*")
        if path.is_file() and path.name != "index.xlsx"
    }


def _remove_empty_dirs(root: Path) -> None:
    for path in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    main()
