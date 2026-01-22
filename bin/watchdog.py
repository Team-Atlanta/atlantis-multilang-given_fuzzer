#!/usr/bin/env python3

import argparse
import logging
import os
import subprocess
import time
from pathlib import Path


def setup_file_log_for_test(logfile: str) -> None:
    logger = logging.getLogger()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(logfile)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)


def log_corpus_status(corpus_dir: str):
    seeds = [
        f
        for f in os.listdir(corpus_dir)
        if os.path.isfile(os.path.join(corpus_dir, f)) and not f.startswith(".")
    ]
    num_seeds = len(seeds)
    logging.info(f"[Corpus] '{corpus_dir}' contains {num_seeds} seeds")


def log_coverage_status(cov_dir: str):
    seeds = [
        f
        for f in os.listdir(cov_dir)
        if os.path.isfile(os.path.join(cov_dir, f))
        and not f.startswith(".")
        and not f.endswith(".cov")
    ]

    missing_cov = []
    for seed in seeds:
        cov_file = os.path.join(cov_dir, seed + ".cov")
        if not os.path.isfile(cov_file):
            missing_cov.append(seed)

    logging.info(f"[Coverage] Total seeds + pov: {len(seeds)}")
    logging.info(f"[Coverage] Seeds or POVs missing .cov files: {len(missing_cov)}")
    if missing_cov:
        logging.info("[Coverage] List of seeds or POVs without .cov files:")
        for seed in missing_cov:
            logging.info(f"[Coverage]   - {seed}")


def log_pov_status(pov_dir: str):
    povs = [
        f
        for f in os.listdir(pov_dir)
        if os.path.isfile(os.path.join(pov_dir, f)) and not f.startswith(".")
    ]
    num_pov = len(povs)
    logging.info(f"[POV] '{pov_dir}' contains {num_pov} povs")


def log_uniafl_status(
    harness_name: str, workdir: str, corpus_dir: str, cov_dir: str, pov_dir: str
):
    logging.info("=" * 100)
    log_corpus_status(corpus_dir)
    log_coverage_status(cov_dir)
    log_pov_status(pov_dir)
    logging.info("=" * 100)


def copy_corpus_to_shared(harness_name: str, corpus_dir: str):
    shared_corpus = (
        Path(os.getenv("SHARED_DIR", "/tmp/")) / harness_name / "uniafl_corpus"
    )
    os.makedirs(str(shared_corpus), exist_ok=True)
    subprocess.run(["rsync", "-a", f"{corpus_dir}/.", str(shared_corpus)], check=False)


def main():
    parser = argparse.ArgumentParser(description="Watchdog script.")
    parser.add_argument(
        "--harness-name",
        dest="harness_name",
        required=True,
        help="Harness name",
    )
    parser.add_argument(
        "--workdir",
        required=True,
        help="Working directory path",
    )
    parser.add_argument(
        "--corpus-dir",
        dest="corpus_dir",
        required=True,
        help="Corpus directory path",
    )
    parser.add_argument(
        "--cov-dir",
        dest="cov_dir",
        required=True,
        help="Coverage directory path",
    )
    parser.add_argument(
        "--pov-dir",
        dest="pov_dir",
        required=True,
        help="Pov directory path",
    )
    parser.add_argument(
        "--interval",
        type=int,
        required=True,
        help="Logging interval in seconds",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    while True:
        log_uniafl_status(
            args.harness_name, args.workdir, args.corpus_dir, args.cov_dir, args.pov_dir
        )
        if os.environ.get('TEST_ROUND', 'False') == 'True':
            copy_corpus_to_shared(args.harness_name, args.corpus_dir)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
