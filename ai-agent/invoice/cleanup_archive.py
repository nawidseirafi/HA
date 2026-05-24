import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = BASE_DIR / "data" / "invoices" / "invoices.db"
DEFAULT_ARCHIVE = BASE_DIR / "data" / "invoices" / "archive"
DEFAULT_BACKUP = BASE_DIR / "data" / "invoices" / "archive_cleanup_backup"


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

    referenced = _referenced_archive_paths(database_path)
    archive_files = _archive_files(archive_dir)
    unreferenced = sorted(archive_files - referenced)
    missing = sorted(referenced - archive_files)

    print(f"Archivdateien: {len(archive_files)}")
    print(f"DB-Referenzen: {len(referenced)}")
    print(f"Unreferenziert: {len(unreferenced)}")
    print(f"DB-Referenzen ohne Datei: {len(missing)}")

    if unreferenced:
        print("\nBeispiele unreferenzierter Dateien:")
        for path in unreferenced[:20]:
            print(f"- {path.relative_to(BASE_DIR)}")

    if missing:
        print("\nBeispiele fehlender referenzierter Dateien:")
        for path in missing[:20]:
            print(f"- {path}")

    if not args.apply:
        print("\nDry run. Mit --apply werden unreferenzierte Dateien in den Backup-Ordner verschoben.")
        return

    run_backup_dir = backup_dir / datetime.now().strftime("%Y%m%dT%H%M%S")
    moved = 0
    for source in unreferenced:
        relative = source.relative_to(archive_dir)
        target = run_backup_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved += 1

    _remove_empty_dirs(archive_dir)
    print(f"\nVerschoben: {moved}")
    print(f"Backup: {run_backup_dir}")


def _resolve(path: Path) -> Path:
    path = path.expanduser()
    if path.is_absolute():
        return path.resolve()
    return (BASE_DIR / path).resolve()


def _referenced_archive_paths(database_path: Path) -> set[Path]:
    if not database_path.exists():
        raise FileNotFoundError(f"Datenbank nicht gefunden: {database_path}")

    con = sqlite3.connect(database_path)
    try:
        rows = con.execute(
            """
            select archive_path
            from invoices
            where status = 'archived' and archive_path is not null and archive_path != ''
            """
        ).fetchall()
    finally:
        con.close()

    return {Path(row[0]).expanduser().resolve() for row in rows}


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
