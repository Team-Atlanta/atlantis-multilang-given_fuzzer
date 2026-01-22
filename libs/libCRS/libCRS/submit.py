"""
Simplified POV submission for OSS-CRS.
- Deduplicates POVs using SQLite (by sanitizer_output hash)
- Copies unique POVs to the artifacts directory
- No VAPI/HTTP submission
"""
import argparse
import hashlib
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path

from .util import get_env
from .paths import CRSPaths


WORKDIR = Path(get_env("CRS_WORKDIR", must_have=True, default="/crs-workdir/"))


def file_hash(path: Path) -> str:
    """SHA1 hash of file content for deduplication."""
    data = b""
    if path.exists():
        with open(path, "rb") as f:
            data = f.read()
    return hashlib.sha1(data).hexdigest()


class SubmitDB:
    """Track submitted POVs with SQLite for deduplication."""

    def __init__(self, workdir: Path | None = None):
        if workdir:
            self.workdir = workdir
        else:
            self.workdir = WORKDIR / "submit"
        os.makedirs(str(self.workdir), exist_ok=True)
        self.db_path = self.workdir / "submit.db"

        self.db = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            check_same_thread=False
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=30000")
        self.__create_db()

    def __get_time(self):
        start_time = int(get_env("START_TIME", must_have=True))
        return int(time.time()) - start_time

    def __create_db(self):
        try:
            self.db.cursor().execute("""
                CREATE TABLE IF NOT EXISTS vd(
                    harness TEXT,
                    pov TEXT,
                    sanitizer_output TEXT,
                    finder TEXT,
                    time INTEGER,
                    UNIQUE(harness, sanitizer_output)
                )
            """)
            self.db.commit()
        except Exception:
            pass

    def __is_duplicate(self, harness: str, sanitizer_output: str) -> bool:
        """Check if this POV was already submitted."""
        res = self.db.cursor().execute(
            "SELECT 1 FROM vd WHERE sanitizer_output = ? AND harness = ?",
            (sanitizer_output, harness),
        )
        return res.fetchone() is not None

    def __record(self, harness: str, pov_path: str, sanitizer_output: str, finder: str):
        """Record POV submission in database."""
        try:
            self.db.cursor().execute(
                "INSERT INTO vd(harness, pov, sanitizer_output, finder, time) VALUES(?,?,?,?,?)",
                (harness, pov_path, sanitizer_output, finder, self.__get_time())
            )
            self.db.commit()
        except sqlite3.IntegrityError:
            pass  # Duplicate, ignore

    def submit_vd(
        self,
        harness: str,
        pov_path: Path,
        sanitizer_output: str,
        finder: str,
    ):
        """Submit POV: deduplicate and copy to artifacts directory."""
        if sanitizer_output == "":
            sanitizer_output = file_hash(pov_path)

        # Check for duplicate
        if self.__is_duplicate(harness, sanitizer_output):
            logging.debug(f"[Submit] Duplicate POV skipped: {pov_path.name}")
            return

        # Copy to POV output directory
        pov_dir = CRSPaths.get_pov_dir() / harness
        os.makedirs(pov_dir, exist_ok=True)

        # Use hash as filename to avoid collisions
        dest_name = f"{sanitizer_output[:16]}_{pov_path.name}"
        dest_path = pov_dir / dest_name

        try:
            shutil.copy2(pov_path, dest_path)
            logging.info(f"[Submit] POV saved: {dest_path}")
        except Exception as e:
            logging.error(f"[Submit] Failed to copy POV: {e}")
            return

        # Record in database
        self.__record(harness, str(dest_path), sanitizer_output, finder)

    def show(self, harness: str = "", fmt: str = "simple"):
        """Show submitted POVs."""
        print(f"\n[DB] {self.db_path}")
        query = "SELECT harness, pov, sanitizer_output, finder, time FROM vd"
        if harness:
            query += f" WHERE harness = '{harness}'"

        res = self.db.cursor().execute(query)
        rows = res.fetchall()

        if not rows:
            print("No POVs submitted yet.")
            return

        print(f"{'Harness':<20} {'Finder':<15} {'Time(s)':<10} {'POV'}")
        print("-" * 80)
        for row in rows:
            h, pov, _, finder, t = row
            pov_name = Path(pov).name if pov else "N/A"
            print(f"{h:<20} {finder:<15} {t:<10} {pov_name}")


def main_submit_vd(args: argparse.Namespace) -> None:
    SubmitDB().submit_vd(
        args.harness,
        args.pov,
        args.sanitizer_output,
        args.finder,
    )


def main_show(args: argparse.Namespace) -> None:
    SubmitDB().show(args.harness)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="POV submission for OSS-CRS")
    subparsers = parser.add_subparsers(title="commands", required=True)

    # Submit VD
    parser_vd = subparsers.add_parser("submit_vd", help="Submit a POV")
    parser_vd.set_defaults(func=main_submit_vd)
    parser_vd.add_argument("--harness", required=True, help="Harness name")
    parser_vd.add_argument("--pov", type=Path, required=True, help="Path to POV file")
    parser_vd.add_argument("--finder", type=str, default="", help="Finder module name")
    parser_vd.add_argument("--sanitizer-output", type=str, default="", help="Crash hash for dedup")

    # Show Status
    parser_show = subparsers.add_parser("show", help="Show submitted POVs")
    parser_show.add_argument("--harness", default="", help="Filter by harness")
    parser_show.set_defaults(func=main_show)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
