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
        """Load seeds from share_dir: both flat files and CRS subdirectories"""
        if not self.share_dir.exists():
            return
        crs_name = os.environ.get("CRS_NAME", "atlantis-multilang-given_fuzzer")
        for entry in self.share_dir.iterdir():
            if entry.is_dir():
                if entry.name == crs_name:
                    continue  # skip our own subdir
                self._load_from(entry)
            else:
                # Flat files from libCRS register-fetch-dir
                self._load_file(entry)

    def _load_file(self, src_seed):
        if src_seed in self.loaded or src_seed.name.startswith(".") or src_seed.name.endswith(".cov"):
            return
        self.loaded.add(src_seed)
        dst = self.our_dst_dir / src_seed.name
        cp(src_seed, dst)

    def _load_from(self, src_dir):
        if not src_dir.exists():
            return
        n = 0
        for src_seed in src_dir.iterdir():
            if src_seed in self.loaded or src_seed.name.startswith(".") or src_seed.name.endswith(".cov"):
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
