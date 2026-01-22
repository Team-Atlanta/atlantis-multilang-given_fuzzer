from abc import ABC, abstractmethod
import asyncio
import logging
import os
from pathlib import Path
import random
import time

from .challenge import CP, CP_Harness
from .config import Config
from .util import (
    BAR,
    async_cp,
    get_env,
    set_env,
    async_run_cmd,
    AsyncNamedLocks,
)

__all__ = ["CRS", "HarnessRunner"]


class CRS(ABC):
    def __init__(
        self,
        name: str,
        hrunner_class,
        config: Config,
        cp: CP,
        workdir: Path | None = None,
    ):
        self.name = name
        self.hrunner_class = hrunner_class
        self.config = config
        self.cp = cp
        if workdir is None:
            workdir = Path(os.environ.get("CRS_WORKDIR", "/crs-workdir/"))
        self.workdir = workdir / "worker-0"
        set_env("CRS_WORKDIR", str(self.workdir))
        set_env("TARGET_CP", str(self.cp.name))
        set_env("START_TIME", str(int(time.time())))

        self.target_harnesses = []
        for harness in self.cp.harnesses.values():
            if self.config.is_target_harness(harness):
                self.target_harnesses.append(harness)

        self.modules = self._init_modules()
        for m in self.modules:
            setattr(self, m.name, m)
        self.prepared = False
        self.submitted = {}
        self.__check_config()

        for m in self.modules:
            if m.is_on():
                m._init()

        self.__async_named_locks = AsyncNamedLocks()
        self.hrunners = []

        # Per-harness saturation tracking
        self.harness_tasks = {}        # {harness_name: asyncio.Task}
        self.harness_states = {}       # {harness_name: state_dict with subprocess, status, etc}

    def log(self, msg: str):
        logging.info(f"[{self.name}] {msg}")

    def error(self, msg: str):
        logging.error(f"[{self.name}] {msg}")
        exit(-1)

    def __check_config(self):
        self.log(BAR())
        self.log("Running options:")
        self.log(f"Target CP: {self.cp.name}")
        self.log(f"Test Mode: {self.config.test}")
        self.log(f"# of cores: {self.config.ncpu}")
        self.log(
            f"Target Harness: {list(map(lambda x: x.name, self.target_harnesses))}"
        )
        self.log(f"Others: {self.config.others}")
        for m in self.modules:
            msg = "ON" if m.is_on() else "OFF"
            self.log(f"{m.name}: {msg}")
        sanitizer = get_env("SANITIZER")
        self.log(f"Sanitizer: {sanitizer}")
        self.log(BAR())
        if sanitizer in [None, ""]:
            self.error("SANITIZER should be set in env")

    async def async_get_lock(self, name: str):
        return await self.__async_named_locks.async_get_lock(name)

    def get_workdir(self, name: str) -> Path:
        workdir = self.workdir / name
        os.makedirs(workdir, exist_ok=True)
        return workdir

    async def async_cp_to_workdir(self, src: Path) -> Path:
        dst = self.workdir / src.name
        await async_cp(src, dst)
        return dst

    def is_submitted(self, harness: CP_Harness, pov_path: Path):
        if not pov_path.exists():
            return True
        key = (harness.name, pov_path.read_bytes())
        if key in self.submitted:
            return True
        self.submitted[key] = True
        return False

    async def async_submit_pov(
        self,
        harness: CP_Harness,
        pov_path: Path,
        sanitizer_output_hash: str = "",
        finder: str = "",
    ):
        if self.is_submitted(harness, pov_path):
            return
        cmd = ["python3", "-m", "libCRS.submit", "submit_vd"]
        cmd += ["--harness", harness.name]
        cmd += ["--pov", pov_path]
        if sanitizer_output_hash:
            cmd += ["--sanitizer-output", sanitizer_output_hash]
        if finder:
            cmd += ["--finder", finder]
        logging.info(f"[{harness.name}][{finder}] Submit pov at {pov_path}")
        await async_run_cmd(cmd, timeout=60)

    def submit_pov(
        self,
        harness: CP_Harness,
        pov_path: Path,
        sanitizer_output_hash: str = "",
        finder: str = "",
    ):
        return asyncio.run(
            self.async_submit_pov(harness, pov_path, sanitizer_output_hash, finder)
        )

    async def async_wait_prepared(self):
        while not self.prepared:
            await asyncio.sleep(1)

    def wait_prepared(self):
        return asyncio.run(self.async_wait_prepared())

    async def async_prepare_modules(self):
        for m in self.modules:
            await m.async_prepare()

    async def __async_prepare(self):
        await self._async_prepare()
        self.prepared = True

    def alloc_cpu(self, hrunners: list["HarnessRunner"]):
        total = self.config.ncpu
        cnt = len(hrunners)
        avg = int(total / cnt)
        mores = random.sample(range(cnt), total % cnt)
        for hrunner in hrunners:
            hrunner.set_ncpu(avg)
        for idx in mores:
            hrunners[idx].set_ncpu(avg + 1)
        core_id = int(os.environ.get("START_CORE_ID", "0"))
        for hrunner in hrunners:
            hrunner.set_core_id(core_id)
            core_id += hrunner.ncpu

    async def async_run(self):
        # Suppress "Future exception was never retrieved" warnings during shutdown
        def handle_exception(loop, context):
            if "exception" in context:
                exc = context["exception"]
                if isinstance(exc, asyncio.CancelledError):
                    return  # Ignore CancelledError during shutdown
            # Log other exceptions
            logging.error(f"Unhandled exception in event loop: {context.get('message', 'Unknown')}")

        asyncio.get_event_loop().set_exception_handler(handle_exception)

        # Phase 1: Prepare (separate from harness tasks)
        await self.__async_prepare()

        # Phase 2: Create harness runners
        hrunners = []
        for harness in self.cp.harnesses.values():
            if not self.config.is_target_harness(harness):
                continue
            hrunners.append(self.hrunner_class(harness, self))
        self.hrunners = hrunners
        self.alloc_cpu(hrunners)

        # Phase 3: Launch harness tasks individually with tracking
        for hrunner in hrunners:
            task = asyncio.create_task(hrunner.async_run())
            self.harness_tasks[hrunner.harness.name] = task
            self.harness_states[hrunner.harness.name] = {
                'task': task,
                'subprocess': None,  # Will be set by UniAFL._async_run
                'last_seed_time': time.time(),
                'status': 'running',
                'seed_count': 0,
                'start_time': time.time()
            }

        # Phase 4: Launch watchdog
        watchdog = asyncio.create_task(self._async_watchdog())

        # Phase 5: Wait for all harness tasks
        try:
            await asyncio.gather(*self.harness_tasks.values(), return_exceptions=True)
        except asyncio.CancelledError:
            pass  # Expected when _async_terminate_gracefully cancels all tasks
        finally:
            # Cleanup watchdog
            if not watchdog.done():
                watchdog.cancel()
                try:
                    await watchdog
                except asyncio.CancelledError:
                    pass

    def run(self):
        if os.environ.get("RUN_SHELL") != None:
            os.system("bash")
        else:
            asyncio.run(self.async_run())

    @abstractmethod
    async def _async_prepare(self):
        pass

    @abstractmethod
    async def _async_watchdog(self):
        pass

    @abstractmethod
    def _init_modules(self) -> list["Module"]:
        pass


class HarnessRunner(ABC):
    def __init__(self, harness: CP_Harness, crs: CRS):
        self.crs = crs
        self.harness = harness
        self.workdir = self.crs.get_workdir(f"HarnessRunner/{self.harness.name}")
        self.ncpu = None
        self.core_ids = None

    def set_ncpu(self, ncpu: int):
        self.ncpu = ncpu

    def set_core_id(self, core_id):
        self.core_ids = list(range(core_id, core_id + self.ncpu))

    def log(self, msg: str):
        logging.info(f"[{self.harness.name}] {msg}")

    def get_workdir(self, name: str) -> Path:
        ret = self.workdir / name
        os.makedirs(ret, exist_ok=True)
        return ret

    async def async_submit_pov(
        self, pov_path: Path, sanitizer_output_hash: str = "", finder: str = ""
    ):
        return await self.crs.async_submit_pov(
            self.harness, pov_path, sanitizer_output_hash, finder
        )

    def submit_pov(
        self, pov_path: Path, sanitizer_output_hash: str = "", finder: str = ""
    ):
        return asyncio.run(
            self.async_submit_pov(pov_path, sanitizer_output_hash, finder)
        )

    async def async_submit_povs(self, pov_dir: Path, finder: str = ""):
        for pov in pov_dir.iterdir():
            await self.crs.async_submit_pov(self.harness, pov, finder=finder)

    async def async_loop_submit_povs(self, pov_dir: Path, finder: str = ""):
        try:
            while True:
                await asyncio.sleep(10)
                await self.async_submit_povs(pov_dir, finder)
        except asyncio.CancelledError:
            await self.async_submit_povs(pov_dir, finder)

    @abstractmethod
    async def async_run(self):
        pass
