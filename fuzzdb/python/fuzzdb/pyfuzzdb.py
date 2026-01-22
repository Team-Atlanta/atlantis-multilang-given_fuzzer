import json
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


class CovInfo:
    def __init__(self, func_name, src, lines):
        self.func_name = func_name
        self.src = src
        self.lines = lines

    def __str__(self):
        return f"func_name: {self.func_name}, src: {self.src}, lines: {self.lines}"


@dataclass
class Seed:
    name: str
    directory: Path
    created_time: int


class FuzzDB:
    def __init__(self, conf_path):
        with open(conf_path, "r") as f:
            conf = json.load(f)
        self.cov_dir = Path(conf["cov_dir"])
        self.corpus_dir = Path(conf["corpus_dir"])
        self.pov_dir = Path(conf["pov_dir"])
        self.harness_name = conf["harness_name"]

        self.node_covs = {}

    # Keep this for mlla
    def list_seeds(self) -> list[str]:
        corpus = os.listdir(str(self.corpus_dir))
        covs = os.listdir(str(self.cov_dir))
        return list(
            map(
                lambda x: x[:-4],
                filter(lambda x: x.endswith(".cov") and x[:-4] in corpus, covs),
            )
        )

    def list_seeds_new(self) -> List[Seed]:
        corpus = os.listdir(str(self.corpus_dir))
        pov = os.listdir(str(self.pov_dir))
        covs = os.listdir(str(self.cov_dir))

        all_seeds = []
        for fname in covs:
            if fname.endswith(".cov"):
                seed_name = fname[:-4]
                if seed_name in corpus:
                    all_seeds.append(
                        Seed(name=seed_name, directory=self.corpus_dir, created_time=-1)
                    )
                elif seed_name in pov:
                    all_seeds.append(
                        Seed(name=seed_name, directory=self.pov_dir, created_time=-1)
                    )
        return all_seeds

    def load_node_cov(self, seed_name: str) -> dict[str, CovInfo]:
        if seed_name in self.node_covs:
            return self.node_covs[seed_name]
        cov_file = self.cov_dir / f"{seed_name}.cov"
        try:
            with open(cov_file) as f:
                data = json.load(f)
                covs = {}
                for func_name in data:
                    d = data[func_name]
                    covs[func_name] = CovInfo(func_name, d["src"], d["lines"])
                self.node_covs[seed_name] = covs
                return covs
        except:
            return {}

    def load_func_cov(self, seed_name) -> list[str]:
        return list(self.load_node_cov(seed_name).keys())

    def load_raw_cov(self, seed_name) -> list[int]:
        cov_name = self.cov_dir / seed_name
        if not cov_name.exists():
            return []
        ret = []
        with open(cov_name, "rb") as f:
            while True:
                tmp = f.read(4)
                if len(tmp) != 4:
                    break
                tmp = struct.unpack("<I", tmp)[0]
                ret.append(tmp)
        return ret

    def check(self):
        for seed in self.list_seeds_new():
            for func_name, info in self.load_node_cov(seed.name).items():
                if not Path(info.src).exists():
                    print(info.src, "does not exist")
                assert Path(info.src).exists()


if __name__ == "__main__":
    FuzzDB(sys.argv[1]).check()
