#!/usr/bin/env python3

import os
import time
import subprocess
import logging
import argparse
from pathlib import Path


def cp(src, dst):
    return subprocess.run(["cp", str(src), str(dst)], check=False)


class SeedShare:
    def __init__(self, workdir, harness_name, share_dir, our_dst_dir):
        self.workdir = Path(workdir)
        self.harness_name = harness_name
        self.share_dir = Path(share_dir)
        self.our_dst_dir = Path(our_dst_dir)
        self.loaded = set()

    def info(self, msg):
        logging.info(f"[SeedShare][{self.harness_name}] {msg}")

    def sync(self):
        self.copy_all_others_to_ours()

    def copy_all_others_to_ours(self):
        """OSS-CRS: read from ALL /seed_share_dir/*/ directories"""
        if not self.share_dir.exists():
            return
        crs_name = os.environ.get("CRS_NAME", "atlantis-multilang-given_fuzzer")
        for crs_dir in self.share_dir.iterdir():
            if not crs_dir.is_dir():
                continue
            if crs_dir.name == crs_name:
                continue  # skip our own
            self._load_from(crs_dir)

    def _load_from(self, src_dir):
        if not src_dir.exists():
            return
        n = 0
        for src_seed in src_dir.iterdir():
            if src_seed in self.loaded or src_seed.name.startswith("."):
                continue
            self.loaded.add(src_seed)
            dst = self.our_dst_dir / src_seed.name
            cp(src_seed, dst)
            n += 1
        if n:
            self.info(f"Loaded {n} seeds from {src_dir}")


def main():
    parser = argparse.ArgumentParser(description="seed sharing script")
    parser.add_argument("--harness-name", dest="harness_name", required=True)
    parser.add_argument("--share-dir", dest="share_dir", required=True)
    parser.add_argument("--workdir", dest="workdir", required=True)
    parser.add_argument("--our-dst-dir", dest="our_dst_dir", required=True)
    parser.add_argument("--interval", type=int, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    share = SeedShare(
        args.workdir,
        args.harness_name,
        args.share_dir,
        args.our_dst_dir,
    )

    while True:
        time.sleep(args.interval)
        share.sync()


if __name__ == "__main__":
    main()
