"""Explicit database lifecycle operations. Never overwrite a backup/restore target."""

import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

from .app.config import Settings
from .app.content import make_chapter
from .app.store import Store


def backup_sqlite(source: Path, destination: Path):
    source = source.resolve(strict=True)
    if destination.exists():
        raise FileExistsError("Destination exists; refusing to overwrite it")
    source_uri = "file:" + quote(str(source)) + "?mode=ro"
    with sqlite3.connect(source_uri, uri=True) as original:
        if original.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Source database failed integrity validation")
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(destination) as target:
            original.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup failed integrity validation; source is unchanged")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    commands.add_parser("migrate")
    backup = commands.add_parser("backup-sqlite")
    backup.add_argument("source", type=Path)
    backup.add_argument("destination", type=Path)
    args = parser.parse_args()
    if args.operation == "migrate":
        store = Store(Settings.from_env().database_url, make_chapter())
        store.close()
        print("Schema 3 ready (schema 1/2 upgrades preserve saves); incompatible versions are refused")
    else:
        backup_sqlite(args.source, args.destination)
        print("Integrity-checked database copy created; no existing file overwritten")


if __name__ == "__main__":
    main()
