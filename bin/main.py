#!/usr/bin/env python3

import asyncio
import glob
import json
import logging
import os
import shlex
import sys
import time
from pathlib import Path

import yaml
from libCRS import CRS, Config, HarnessRunner, Module, init_cp_in_runner, util
from libCRS.util import TestResult
from redis import Redis

sys.path.insert(0, "/usr/local/bin/symbolizer")
from llvm_symbolizer import LLVMSymbolizer


def dict_to_json(data):
    def skip_str(x):
        for ty in [int, list, dict]:
            if isinstance(x, ty):
                return True
        return False

    def map_str(x):
        return (x[0], x[1] if skip_str(x[1]) else str(x[1]))

    data = dict(map(map_str, data.items()))
    return json.dumps(data)


def get_seed_share_dir():
    return os.getenv("SEED_SHARE_DIR", "/seed_share_dir")


class FuzzerOpt:
    def __init__(self, harness_name):
        self.harness_name = harness_name
        self.opt = None

    async def get_run_fuzzer_opt(self):
        opt_file = Path(os.environ.get("OUT", "/out/")) / f"{self.harness_name}.options"
        if opt_file.exists():
            opt = opt_file.read_text()
            CLOSE_FD = "close_fd_mask"
            if CLOSE_FD in opt:
                new = ""
                for line in opt.split("\n"):
                    if CLOSE_FD in line:
                        continue
                    new += line + "\n"
                opt_file.write_text(new)
        env = os.environ.copy()
        env["SKIP_SEED_CORPUS"] = "1"
        cmd = ["get_run_fuzzer_opt", self.harness_name]
        ret = await util.async_run_cmd(cmd, env=env)
        self.opt = shlex.split(ret.stdout.decode("utf-8", errors="ignore"))[1:]
        return self

    def get_max_len(self):
        default = 4096
        for opt in self.opt:
            if opt.startswith("-max_len"):
                try:
                    return min(int(opt.split("=")[-1]), 1024 * 1024)  # max 1MB
                except:
                    pass
        return default

    def is_timeout_bug_allowed(self):
        return "-timeout_exitcode=0" not in self.opt


class UniAFL(Module):
    BASE = Path("/home/crs/uniafl/")
    BIN = BASE / "target/release/uniafl"
    DIFF_PATH = Path("/src/ref.diff")

    def _init(self) -> None:
        self.redis_url = {}
        self.fuzzer_opts = {}
        self.port = 22222
        self.tests_without_harness = [self._async_test_once]
        self.tests_with_harness = [
            self._async_test_executor,
            self._async_test_given_fuzzer,
        ]
        asyncio.run(self.__async_prepare_executor_all())

    def run_redis(self, harness):
        port = self.port
        url = f"localhost:{port}"
        self.port += 1
        os.system(
            f"redis-server --port {port} --bind localhost --daemonize yes > /dev/null"
        )
        self.redis_url[harness.name] = url
        return url

    async def __async_get_fuzzer_opt(self, harness_name):
        if harness_name in self.fuzzer_opts:
            return self.fuzzer_opts[harness_name]
        ret = await FuzzerOpt(harness_name).get_run_fuzzer_opt()
        self.fuzzer_opts[harness_name] = ret
        return ret

    async def __async_prepare_executor_all(self):
        tasks = []
        for harness in self.crs.target_harnesses:
            tasks.append(self.__async_prepare_executor(harness))
        await asyncio.gather(*tasks)

    async def __async_prepare_executor(self, harness):
        workdir = Path(f"/executor/{harness.name}")
        dummy_dir = workdir / "dummy"
        for name in ["uniafl_corpus", "uniafl_cov", "others_corpus", "pov", "workdir"]:
            os.makedirs(str(dummy_dir / name), exist_ok=True)
        os.system(f"chmod -R a+w '{workdir}'; chmod -R +t '{workdir}'")
        fuzzer_opt = await self.__async_get_fuzzer_opt(harness.name)
        max_len = fuzzer_opt.get_max_len()
        config = {
            "project_src_dir": self.crs.cp.cp_src_path,
            "harness_src_path": harness.src_path,
            "given_fuzzer_dir": self.crs.cp.built_path,
            "corpus_dir": dummy_dir / "uniafl_corpus",
            "cov_dir": dummy_dir / "uniafl_cov",
            "given_corpus_dir": dummy_dir / "others_corpus",
            "pov_dir": Path(os.environ.get("POV_DIR", "/artifacts/povs")),
            "workdir": dummy_dir / "workdir",
            "language": self.crs.cp.language,
            "redis_url": self.run_redis(harness),
            "ms_per_exec": 0,
            "max_len": max_len,
            "allow_timeout_bug": fuzzer_opt.is_timeout_bug_allowed(),
        }
        for core_id in range(self.crs.config.ncpu):
            name = f"{harness.name}_executor_{core_id}"
            config["harness_name"] = name
            config["harness_path"] = harness.bin_path
            config["core_ids"] = [core_id]
            config_path = workdir / f"config_{core_id}"
            config_path.write_text(dict_to_json(config))
        await self.__async_prepare_coverage(harness)

    async def __async_prepare_coverage(self, harness):
        self.log(f"Prepare coverage map for {harness.name}")
        if self.crs.cp.language == "jvm":
            redis_url = self.redis_url[harness.name]
            cmd = [
                "run_fuzzer",
                harness.name,
                "--uniafl_coverage",
                "--uniafl_prepare",
                f"--redis_url={redis_url}",
            ]
            env = os.environ.copy()
            env["JAZZER_MAX_NUM_COUNTERS"] = str(128 << 20)
            await util.async_run_cmd(cmd, env=env)
        elif self.crs.cp.language in ["c", "cpp", "c++", "rust", "go"]:
            if os.environ.get("CREATE_CONF") != None:
                self.log("Skip because create_conf_mod")
                return
            redis_url = self.redis_url[harness.name]
            cmd = f"cfg_analyzer.py"
            cmd += f" --harness {harness.bin_path}"
            cmd += f" --redis_url {redis_url}"
            ncpu = self.crs.config.ncpu // len(self.crs.target_harnesses)
            ncpu = 1 if ncpu < 1 else ncpu
            cmd += f" --ncpu {ncpu}"
            env = os.environ.copy()
            await util.async_run_cmd(cmd.split(" "), env=env)

    def is_log_mode(self) -> bool:
        return os.environ.get("LOG") == "True"

    async def _async_prepare(self) -> None:
        if self.is_log_mode():
            await util.async_run_cmd(
                "cargo build --features log --release".split(" "), cwd=str(UniAFL.BASE)
            )

    async def _async_get_mock_result(self, hrunner: HarnessRunner | None):
        pass

    async def _async_run_watchdog(self, hrunner: HarnessRunner | None):
        if hrunner == None:
            return
        workdir = hrunner.get_workdir(self.name)
        watchdog_cmd = [
            "watchdog.py",
            "--harness-name",
            hrunner.harness.name,
            "--workdir",
            hrunner.get_workdir(f"{workdir.name}/workdir"),
            "--corpus-dir",
            hrunner.uniafl_corpus_dir,
            "--cov-dir",
            hrunner.uniafl_cov_dir,
            "--pov-dir",
            hrunner.pov_dir,
            "--interval",
            600,
        ]
        return await util.async_run_cmd(watchdog_cmd)

    async def _async_run_seed_share(self, hrunner: HarnessRunner | None):
        if hrunner == None:
            return
        share_dir = get_seed_share_dir()
        cmd = [
            "seed_share.py",
            "--harness-name",
            hrunner.harness.name,
            "--workdir",
            hrunner.get_workdir(f"{self.name}/seed_share_workdir"),
            "--share-dir",
            share_dir,
            "--our-dst-dir",
            hrunner.others_corpus_dir,
            "--interval",
            300,
        ]
        return await util.async_run_cmd(cmd)

    async def _async_run_cleaner(self, hrunner: HarnessRunner | None):
        if hrunner == None:
            return
        if self.crs.cp.language != "jvm":
            return
        cmd = [
            "jazzer_cleaner.py",
        ]
        return await util.async_run_cmd(cmd)

    async def _async_run(self, hrunner: HarnessRunner | None):
        workdir = hrunner.get_workdir(self.name)
        config_path = await self.__prepare_config(hrunner)
        cmd = ["setarch", "x86_64", "-R", UniAFL.BIN, "--config", config_path]
        env = os.environ.copy()
        env["UNIAFL_CONFIG"] = str(config_path)
        if self.is_log_mode():
            log_file = hrunner.get_workdir(f"{self.name}/workdir") / "log"
            self.logH(hrunner, "Check logfile: " + str(log_file))
        self.logH(hrunner, "Run UniAFL")

        # Spawn subprocess directly to get handle for per-harness shutdown
        proc = await asyncio.create_subprocess_exec(
            *[str(c) for c in cmd],
            cwd=str(workdir),
            env=env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Launch support tasks
        watchdog = asyncio.create_task(self._async_run_watchdog(hrunner))
        cleaner = asyncio.create_task(self._async_run_cleaner(hrunner))
        seed_share = asyncio.create_task(self._async_run_seed_share(hrunner))

        # Wait for process to complete
        out, err = await proc.communicate()

        # Log result
        self.logH(hrunner, f"UniAFL process exited: returncode={proc.returncode}")
        if proc.returncode != 0 and err:
            self.logH(hrunner, f"stderr: {err.decode('utf-8', errors='replace')}")

        # Cleanup support tasks
        for task in [watchdog, seed_share, cleaner]:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _async_test_once(self) -> list[TestResult]:
        cmd = ["cargo", "test", "--release", "--bin", "uniafl"]
        ret = await util.async_run_cmd(cmd, cwd=str(UniAFL.BASE))
        return ret.to_test_result("Some Test")

    async def _clear_dirs(self, hrunner):
        for dir in [
            hrunner.uniafl_corpus_dir,
            hrunner.uniafl_cov_dir,
            hrunner.others_corpus_dir,
        ]:
            await util.async_run_cmd(["rm", "-rf", str(dir)])
            os.makedirs(str(dir), exist_ok=True)

    async def _async_cargo_test(
        self,
        hrunner,
        test_name,
        des,
        more_conf={},
        given_env={},
        timeout=300,
    ) -> TestResult:
        await self._clear_dirs(hrunner)
        config_path = await self.__prepare_test_config(hrunner, more_conf)
        env = os.environ.copy()
        env["UNIAFL_CONFIG"] = str(config_path)
        env["TEST_TIMEOUT"] = str(timeout)
        for k, v in given_env.items():
            env[k] = str(v)
        cmd = ["setarch", "x86_64", "-R"]
        cmd += [
            "cargo",
            "test",
            test_name,
            "--release",
            "--bin",
            "uniafl",
            "--",
            "--test-threads=1",
            "--nocapture",
            "--ignored",
        ]
        ret = await util.async_run_cmd(cmd, cwd=str(UniAFL.BASE), env=env)
        return ret.to_test_result(des)

    async def _async_test_executor(self, hrunner: HarnessRunner) -> TestResult:
        return await self._async_cargo_test(
            hrunner, "executor::tests", "Executor Module Tests"
        )

    async def _async_test_given_fuzzer(self, hrunner: HarnessRunner) -> TestResult:
        more_conf = {"input_gens": ["given_fuzzer"]}
        ret = await self._async_cargo_test(
            hrunner,
            "msa::tests::check_fuzzer",
            "Given Fuzzer Tests",
            more_conf=more_conf,
            timeout=900,
        )
        return ret


    async def __prepare_test_config(self, hrunner, more={}):
        config = {}
        workdir = hrunner.get_workdir(self.name) / "test"
        config["povs"] = await self.__cp_internal(
            workdir, "povs", hrunner.harness.get_answer_povs()
        )
        config["seeds"] = await self.__cp_internal(
            workdir, "seeds", hrunner.harness.get_answer_seeds()
        )
        config["core_ids"] = hrunner.core_ids[:2]
        for seed in hrunner.harness.get_answer_seeds():
            await util.async_cp(seed, hrunner.others_corpus_dir / seed.name)
        for k, v in more.items():
            config[k] = v
        return await self.__prepare_config(hrunner, config)

    async def __prepare_config(self, hrunner, more={}):
        workdir = hrunner.get_workdir(self.name)
        fuzzer_opt = await self.__async_get_fuzzer_opt(hrunner.harness.name)
        max_len = fuzzer_opt.get_max_len()
        config = {
            "project_src_dir": self.crs.cp.cp_src_path,
            "harness_name": hrunner.harness.name,
            "harness_path": hrunner.harness.bin_path,
            "harness_src_path": hrunner.harness.src_path,
            "given_fuzzer_dir": self.crs.cp.built_path,
            "corpus_dir": hrunner.uniafl_corpus_dir,
            "cov_dir": hrunner.uniafl_cov_dir,
            "given_corpus_dir": hrunner.others_corpus_dir,
            "pov_dir": hrunner.pov_dir,
            "workdir": hrunner.get_workdir(f"{workdir.name}/workdir"),
            "core_ids": hrunner.core_ids,
            "language": self.crs.cp.language,
            "redis_url": self.redis_url[hrunner.harness.name],
            "ms_per_exec": hrunner.ms_per_exec,
            "max_len": max_len,
            "allow_timeout_bug": fuzzer_opt.is_timeout_bug_allowed(),
        }
        if UniAFL.DIFF_PATH.exists():
            config["diff_path"] = str(UniAFL.DIFF_PATH)
            process_diff_path = Path("/src/ref.diff.json")
            await util.async_run_cmd(
                ["extract_from_diff.py", UniAFL.DIFF_PATH, process_diff_path]
            )
            if process_diff_path.exists():
                config["processed_diff_path"] = str(process_diff_path)
        dic = hrunner.harness.get_given_dict()
        if dic != None:
            config["given_dict_path"] = dic
            self.logH(hrunner, f"Pass the given dict in {dic} to UniAFL")
        if "input_gens" in self.crs.config.others:
            config["input_gens"] = self.crs.config.others["input_gens"]
        for k, v in more.items():
            config[k] = v
        config_path = workdir / "config"
        config_path.write_text(dict_to_json(config))
        hrunner.uniafl_config_path = config_path
        self.logH(hrunner, f"Prepare config file: {config_path}")
        return config_path

    async def __cp_internal(self, workdir, name, files):
        ret = []
        dst_dir = workdir / f"internal/{name}"
        for file in files:
            dst = dst_dir / file.name
            await util.async_cp(file, dst)
            ret.append(str(dst))
        return ret


class AnyHR(HarnessRunner):
    async def async_run(self):
        # OSS-CRS output paths
        self.pov_dir = Path(os.environ.get("POV_DIR", "/artifacts/povs"))
        os.makedirs(str(self.pov_dir), exist_ok=True)
        corpus_base = Path(os.environ.get("CORPUS_DIR", "/artifacts/corpus"))
        os.makedirs(str(corpus_base), exist_ok=True)
        self.uniafl_corpus_dir = corpus_base
        crs_data_dir = Path(os.environ.get("CRS_DATA_DIR", "/artifacts/crs-data"))
        self.uniafl_cov_dir = crs_data_dir / "coverage"
        os.makedirs(str(self.uniafl_cov_dir), exist_ok=True)
        self.uniafl_config_path = None
        self.others_corpus_dir = self.get_workdir("others_corpus")
        await self.__unzip_given_corpus(self.others_corpus_dir)
        await self.__copy_corpus_from_other_cp(self.others_corpus_dir)
        self.ms_per_exec = await self.__async_get_ms_per_exec()
        await self.crs.uniafl.async_run(self)

    async def __copy_corpus_from_other_cp(self, dst):
        """OSS-CRS: load initial seeds from all /seed_share_dir/*/ directories"""
        seed_share_dir = Path(get_seed_share_dir())
        if not seed_share_dir.exists():
            return
        crs_name = os.environ.get("CRS_NAME", "atlantis-multilang-given_fuzzer")
        candidates = [
            d for d in seed_share_dir.iterdir()
            if d.is_dir() and d.name != crs_name
        ]
        if len(candidates) == 0:
            self.log(f"No reusable corpus found for {self.harness.name}")
            return
        for candidate in candidates:
            if candidate.is_dir():
                await util.async_cp(candidate, dst)
                self.log(f"Reuse corpus from {candidate}")

    async def __unzip_given_corpus(self, dst):
        corpus = self.harness.get_given_corpus()
        if corpus == None:
            self.log("No given corpus")
            return
        tmp = f"/tmp/{self.crs.cp.name}_{self.harness.name}_given_corpus"
        os.makedirs(tmp, exist_ok=True)
        await util.async_run_cmd(f"unzip -o -d {tmp}/ {corpus}".split(" "))
        names = {}
        total = 0
        for file in glob.glob(f"{tmp}/**/*", recursive=True):
            file = Path(file)
            if file.is_dir():
                continue
            name = file.name
            if name in names:
                n = names[name]
                names[name] += 1
                name = f"{name}_duplicated_{n}"
            else:
                names[name] = 1
            file.rename(dst / name)
            total += 1
        self.log(f"Extract {total} seed from {corpus} and save into {dst}")

    async def __async_get_ms_per_exec(self):
        tmp = self.workdir / "tmp"
        tmp.write_text("A")
        core = self.core_ids[0]
        cmd = [
            "taskset",
            "-c",
            str(core),
            "reproduce",
            self.harness.name,
            "-timeout=100",
        ]
        key = bytes(f"Executed {tmp} in", "utf-8")
        ms = 0
        env = os.environ.copy()
        env["TESTCASE"] = f"{tmp} {tmp}"
        for i in range(5):
            ret = await util.async_run_cmd(cmd, env=env)
            if key not in ret.stderr:
                continue
            ms = int(ret.stderr.split(key)[-1].split(b" ms")[0])
            break
        self.log(f"{ms} ms/exec")
        return ms


class AnyCRS(CRS):
    def _init_modules(self) -> list[Module]:
        return [UniAFL("uniafl", self)]

    async def _async_prepare(self):
        await self.async_prepare_modules()

    async def _async_watchdog(self):
        """Run indefinitely - outer framework handles termination."""
        while True:
            await asyncio.sleep(3600)


################################################################################


def wait_redis(redis_url):
    r = Redis.from_url(redis_url)
    while True:
        try:
            if r.ping():
                break
            time.sleep(1)
        except:
            pass


def handle_no_fdp(conf, cp):
    if "no_FDP" in conf.others:
        if conf.target_harnesses:
            targets = conf.target_harnesses
        else:
            targets = cp.get_harnesses().keys()
        targets = list(filter(lambda x: not x.endswith("FDP"), targets))
        conf.target_harnesses = targets


def name_filter(target, names):
    return True


def create_conf(cp, conf_path, answer_path_if_exist):
    dummy = Path("/tmp/dummy_for_conf")
    dummy.write_text("\n")
    KEY = "fuzzerTestOneInput"
    if cp.language == "jvm":
        KEY = "fuzzerTestOneInput"
    else:
        KEY = "LLVMFuzzerTestOneInput"

    def normalize_src(src):
        for prefix, key in [("/src/repo", "$REPO"), ("/src", "$PROJECT")]:
            if src.startswith(prefix):
                return key + src[len(prefix) :]
        return src

    conf = {}

    async def get_key_addr(harness):
        cmd = f"nm {harness.bin_path} | grep LLVMFuzzerTestOneInput"
        ret = await util.async_run_cmd(["/bin/bash", "-c", cmd])
        try:
            return int(ret.stdout.decode("utf-8").split(" ")[0], 16)
        except:
            return None

    async def llvm_symbolzer_based(name, harness):
        harness.cp.log("try llvm_symbolzer_based")
        key_addr = await get_key_addr(harness)
        if key_addr == None:
            return
        symbolizer = LLVMSymbolizer(str(harness.bin_path), "/out/llvm-symbolizer")
        ret = symbolizer.run_llvm_symbolizer_addr(key_addr)
        conf[name] = normalize_src(ret.src_file)

    async def get_dummy_cov(harness, idx):
        dummy_seed = Path(f"/tmp/dummy_for_conf_{idx}")
        dummy_seed.write_text("\n")
        for i in range(2):
            env = os.environ.copy()
            env["CUR_WORKER"] = str(idx + i)
            cmd = f"timeout 5m run_once {harness.name} {dummy_seed}"
            ret = await util.async_run_cmd(["/bin/bash", "-c", cmd], env=env)
            cov_file = Path(str(dummy_seed) + ".cov")
            if cov_file.exists():
                return json.loads(cov_file.read_text())
        return None

    async def update_conf(name, harness, idx):
        if harness.cp.language != "jvm":
            return await llvm_symbolzer_based(name, harness)
        covs = await get_dummy_cov(harness, idx)
        if covs == None or len(covs) == 0:
            for key in ["/src/repo/", "/src/"]:
                key = key + f"**/{harness.name}.java"
                cands = glob.glob(key, recursive=True)
                if len(cands) > 0:
                    conf[name] = normalize_src(cands[0])
                    break
            return
        for func in covs:
            if KEY in func:
                src = covs[func]["src"]
                conf[name] = normalize_src(src)
                break

    async def update_all(cp):
        jobs = []
        idx = 0
        for name, harness in cp.harnesses.items():
            jobs.append(update_conf(name, harness, idx))
            idx += 1
        await asyncio.gather(*jobs)

    asyncio.run(update_all(cp))

    to_yaml = []
    with open(conf_path, "w") as f:
        for name in conf:
            to_yaml.append({"name": name, "path": conf[name]})
        yaml.dump({"harness_files": to_yaml}, f)
    cp.log("Created Conf>\n" + conf_path.read_text())

    if os.getenv("CRS_TEST") == "True" and answer_path_if_exist.exists():
        with open(answer_path_if_exist, "r") as f:
            answer_conf = yaml.safe_load(f)["harness_files"]
            for answer in answer_conf:
                name = answer["name"]
                path = answer["path"]
                abs_path = Path(
                    path.replace("$REPO", "/src/repo").replace("$PROJECT", "/src")
                )
                assert abs_path.exists(), f"Path {path} ({abs_path}) does not exist"
                assert name in conf, f"{name} not in conf"
                ours = Path(
                    str(conf[name])
                    .replace("$REPO", "/src/repo")
                    .replace("$PROJECT", "/src")
                )
                assert ours.exists(), f"Our answer {ours} does not exist"
                assert ours.read_text() == abs_path.read_text()
            cp.log("Same as the answer conf!")

    cp.log("DONE")

    return conf


def add_env(key, value, replace=None):
    opt = os.environ.get(key, "")
    if opt == "":
        opt = value
    else:
        if replace != None:
            if replace in opt:
                opt = opt.replace(replace, value)
            else:
                opt = value + ":" + opt
        else:
            opt = value + ":" + opt
    util.set_env(key, opt)


CONF_PATH = Path("/src/.aixcc/config.yaml")
TMP_CONF = Path("/src/.aixcc/config.yaml.tmp")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    conf = Config(0, 1).load("/crs.config")
    shm_size = len(os.sched_getaffinity(0)) * 4
    os.system(f"mount -o remount,size={shm_size}G /dev/shm")
    os.system("touch /dev/shm/aa")
    shm = Path("/dev/shm")
    prevs = list(shm.iterdir())
    if len(prevs) > 0:
        print("clean up /dev/shm")
        for name in prevs:
            os.system(f"rm -rf {name}")

    add_env("ASAN_OPTIONS", "detect_leaks=0", "detect_leaks=1")
    conf_create_mode = os.environ.get("CREATE_CONF", False) != False
    if conf_create_mode:
        if CONF_PATH.exists():
            CONF_PATH.rename(TMP_CONF)
    cp = init_cp_in_runner()

    if conf_create_mode:
        names = list(cp.harnesses.keys())
        for name in names:
            if not name_filter(name, names):
                del cp.harnesses[name]
    else:
        handle_no_fdp(conf, cp)

    crs = AnyCRS("CRS-Multilang", AnyHR, conf, cp)
    if conf_create_mode:
        output_path = Path(os.environ.get("CREATE_CONF"))
        create_conf(cp, output_path, TMP_CONF)
        exit(0)

    redis_url = os.environ.get("CODE_INDEXER_REDIS_URL")
    if redis_url:
        crs.log(f"Code Indexer REDIS URL: {redis_url}")
        wait_redis(redis_url)
        crs.log(f"Code Indexer REDIS is available")
    crs.run()
