import os
import logging
import json
import base64
import asyncio
from pathlib import Path
from .ossfuzz_lib import get_harness_names


__all__ = ["CP_Harness", "CP", "init_cp_in_runner"]

UNIAFL_BIN = Path("/home/crs/uniafl/target/release/uniafl")


class CP_Harness:
    def __init__(self, cp: "CP", name: str, bin_path: Path):
        self.cp = cp
        self.name = name
        self.bin_path = bin_path
        self.runner = None
        self._loop = None

    def get_given_corpus(self) -> Path | None:
        corpus = Path(str(self.bin_path) + "_seed_corpus.zip")
        if corpus.exists():
            return corpus
        return None

    def get_given_dict(self) -> Path | None:
        dic = Path(str(self.bin_path) + ".dict")
        if dic.exists():
            return dic
        return None

    def run_input(
        self, file_path, worker_idx="0"
    ) -> (bytes, bytes, bytes | None, bytes | None):
        """
        DO NOT INVOKE THIS IN MULTI-THREADS
        return (stdout, stderr, cov json data if possible, crash_log if crashed)
        """
        # Check if loop is closed or in invalid state
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

        return self._loop.run_until_complete(
            self.async_run_input(file_path, worker_idx)
        )

    async def async_run_input(
        self, file_path, worker_idx="0"
    ) -> tuple[bytes, bytes, bytes | None, bytes | None]:
        """
        DO NOT INVOKE THIS IN MULTI-THREADS
        return (stdout, stderr, cov json data if possible, crash_log if crashed)
        """
        worker_idx = int(os.environ.get("CUR_WORKER", worker_idx))
        conf_path = Path(f"/executor/{self.name}/config_{worker_idx}")
        if UNIAFL_BIN.exists() and conf_path.exists():
            return await self.__run_fast_reproduce(conf_path, file_path)
        else:
            return await self.__run_reproduce(file_path)

    async def __run_reproduce(
        self, file_path
    ) -> tuple[bytes, bytes, bytes | None, bytes | None]:
        # TODO
        raise Exception("TODO: __run_reproduce")

    async def __run_fast_reproduce(
        self, conf_path, file_path
    ) -> tuple[bytes, bytes, None, None]:
        # TODO: do we need to consider if self.runner != None but uniafl dies?
        if self.runner is None:
            self.runner = await self.__boot_up_fast_reproduce(conf_path)
        self.runner.stdin.write(bytes(str(file_path) + "\n", "utf-8"))
        await self.runner.stdin.drain()
        line = await self.runner.stdout.readline()
        with open(line.strip()) as f:
            out = json.load(f)
        ret = []
        for key in ["stdout", "stderr", "coverage", "crash_log"]:
            if key in out:
                ret.append(base64.b64decode(out[key]))
            else:
                ret.append(None)
        return tuple(ret)

    async def __boot_up_fast_reproduce(self, conf_path) -> asyncio.subprocess.Process:
        cmd = ["setarch", "x86_64", "-R"]
        cmd += [str(UNIAFL_BIN), "-c", conf_path, "-e"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        return proc


class CP:
    def __init__(self, name: str, built_path: str | None):
        from .paths import CRSPaths

        self.name = name
        self.built_path = Path(str(built_path)) if built_path else None
        # Use centralized path resolution for diff file
        self.diff_path = CRSPaths.get_diff_path()
        # Get language from FUZZING_LANGUAGE env var (default: "c")
        self.language = os.environ.get("FUZZING_LANGUAGE", "c")

        self.harnesses = self.get_harnesses()

    def get_harnesses(self) -> dict[str, CP_Harness]:
        """Get harnesses from OSS-Fuzz output directory"""
        harnesses = {}
        for name in get_harness_names(self.built_path):
            bin_path = self.built_path / name if self.built_path else None
            harnesses[name] = CP_Harness(self, name, bin_path)
        return harnesses

    def log(self, msg: str):
        logging.info(f"[CP] {msg}")


def init_cp_in_runner() -> CP:
    from .paths import CRSPaths
    return CP(
        os.environ.get("CRS_TARGET"),
        str(CRSPaths.OUT_DIR)
    )
