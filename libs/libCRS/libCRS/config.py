"""
Simplified configuration for OSS-CRS mode.
Resource limits are handled by OSS-CRS framework via Docker cgroups.
"""
import json
import logging
import os
from pathlib import Path

from .challenge import CP_Harness

__all__ = ["Config"]


class Config:
    def log(self, msg: str):
        logging.info(f"[Config] {msg}")

    def __init__(self):
        self.modules: list[str] | None = None
        self.target_harnesses: list[str] | None = None
        # Support TARGET_HARNESS env var for single harness mode (OSS-CRS)
        if os.environ.get("TARGET_HARNESS"):
            self.target_harnesses = [os.environ.get("TARGET_HARNESS")]
        self.test: bool = bool(os.environ.get("CRS_TEST"))
        self.test_wo_harness: bool = (
            os.environ.get("CRS_TEST_WO_HARNESS", "True") == "True"
        )
        self.ncpu: int = os.cpu_count()  # OSS-CRS handles limits via cgroups
        self.others = {}

    def load(self, conf_path: Path | str):
        """Load optional config file. Returns self for chaining."""
        if isinstance(conf_path, str):
            conf_path = Path(conf_path)
        if not conf_path.exists():
            return self
        with open(conf_path) as f:
            config = json.load(f)
        for key in vars(self):
            if key in config:
                setattr(self, key, config[key])
        return self

    def is_module_on(self, module_name: str) -> bool:
        return self.modules is None or module_name in self.modules

    def is_target_harness(self, harness: CP_Harness) -> bool:
        if self.target_harnesses is None:
            return True
        return harness.name in self.target_harnesses
